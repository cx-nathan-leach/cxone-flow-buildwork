from orchestration.base import AbstractOrchestrator
from orchestration.naming.adoe import AzureDevOpsProjectNaming
import base64, urllib, urllib.parse, re
from jsonpath_ng import parse
from cxone_api.util import CloneUrlParser
from scm_services import SCMService
from pathlib import Path
from cxone_api.high.scans import ScanInspector
from api_utils.auth_factories import EventContext
from cxone_api.util import json_on_ok
from services import CxOneFlowServices
from typing import List, Dict

class AzureDevOpsEnterpriseOrchestrator(AbstractOrchestrator):

    __diag_id = "f844ec47-a9db-4511-8281-8b63f4eaf94e"
    __diagid_query = parse("$.resourceContainers.account.id")
    __remoteurl_query = parse("$.resource.repository.remoteUrl")
    __repo_project_key_query = parse("$.resource.repository.project.name")
    __repo_slug_query = parse("$.resource.repository.name")
    __repo_id_query = parse("$.resource.repository.id")
    __payload_type_query = parse("$.eventType")
    __repository_id_query = parse("$.resource.repository.id")
    __collection_url_query = parse("$.resourceContainers.collection.baseUrl")

    __policy_scope_query = parse("$.value[*].settings.scope[*]")
    __branch_names_query = parse("$.value[*].name")

    
    __push_default_branch_query = parse("$.resource.repository.defaultBranch")
    __push_target_branch_query = parse("$.resource.refUpdates..name")
    __push_target_hash_query = parse("$.resource.refUpdates..newObjectId")


    __pr_draft_query = parse("$.resource.isDraft")
    __pr_self_link_query = parse("$.resource._links.web.href")    
    __pr_tohash_query = parse("$.resource.lastMergeTargetCommit[commitId]")
    __pr_tobranch_query = parse("$.resource.targetRefName")
    __pr_fromhash_query = parse("$.resource.lastMergeSourceCommit[commitId]")
    __pr_frombranch_query = parse("$.resource.sourceRefName")
    __pr_id_query = parse("$.resource.pullRequestId")
    __pr_reviewer_status_query = parse("$.resource.reviewers[*].vote")
    __pr_state_query = parse("$.resource.status")


    @property
    def config_key(self):
        return "adoe"

    def __init__(self, event_context : EventContext):
        AbstractOrchestrator.__init__(self, event_context)

        self.__isdiagnostic = AzureDevOpsEnterpriseOrchestrator.__diag_id in [x.value for x in list(AzureDevOpsEnterpriseOrchestrator.__diagid_query.find(self.event_context.message))]
        if self.__isdiagnostic:
            return

        self.__event = [x.value for x in list(self.__payload_type_query.find(self.event_context.message))][0]
        self.__route_urls = [x.value for x in list(self.__remoteurl_query.find(self.event_context.message))]
        self.__remote_url = self.__route_urls[0]
        self.__default_branches = [AbstractOrchestrator.normalize_branch_name(x.value) for x in list(self.__push_default_branch_query.find(self.event_context.message))]
        self.__repo_key = [x.value for x in list(self.__repo_project_key_query.find(self.event_context.message))][0]
        self.__repo_slug = [x.value for x in list(self.__repo_slug_query.find(self.event_context.message))][0]
        self.__collection_url = [x.value for x in list(self.__collection_url_query.find(self.event_context.message))][0]
        self.__collection = Path(urllib.parse.urlparse(self.__collection_url).path).name
        self.__repo_id = self.__repo_id_query.find(self.event_context.message)[0].value


    @property
    def event_name(self) -> str:
        return self.__event
    
    async def __common_execution_steps(self, services : CxOneFlowServices):
        # Get clone urls from repo details since ADO doesn't include all clone protocols in the event.
        repo_details = json_on_ok(await services.scm.exec("GET", f"/{self.__collection}/{self.__repo_key}/_apis/git/repositories/{self.__repo_slug}"))
        http_clone_url = urllib.parse.urlparse(self.__remote_url)
        self.__clone_urls = {
            http_clone_url.scheme : self.__remote_url,
            "ssh" : repo_details['sshUrl']
        }

    async def execute(self, services : CxOneFlowServices):
        if self.__event not in AzureDevOpsEnterpriseOrchestrator.__workflow_map.keys():
            AzureDevOpsEnterpriseOrchestrator.log().error(f"Unhandled scan event type: {self.__event}")
        else:
            await self.__common_execution_steps(services)
            return await AzureDevOpsEnterpriseOrchestrator.__workflow_map[self.__event](self, services)

    async def handle_delegated_scan(self, services : CxOneFlowServices, scan_id : str):
        if self.__event not in AzureDevOpsEnterpriseOrchestrator.__delegate_scan_handler_map.keys():
            AzureDevOpsEnterpriseOrchestrator.log().error(f"Unhandled delegated scan event type: {self.__event}")
        else:
            self.delegated_scan = True
            await self.__common_execution_steps(services)
            return await AzureDevOpsEnterpriseOrchestrator.__delegate_scan_handler_map[self.__event](self, services, scan_id)

    @property
    def is_diagnostic(self):
        return self.__isdiagnostic

    @property
    def route_urls(self):
        return self.__route_urls

    @property
    def _repo_project_key(self):
        return self.__repo_key

    @property
    def _repo_organization(self) -> str:
        return self.__collection

    @property
    def _repo_name(self):
        return self.__repo_slug

    @property
    def _repo_slug(self):
        return self.__repo_slug

    async def is_signature_valid(self, shared_secret):
        auth = self.get_header_key_safe('Authorization')
        if auth is None:
            AzureDevOpsEnterpriseOrchestrator.log().warning("Authorization header is missing in request, rejecting.")
            return False

        base64_payload = auth.split(" ")[-1:].pop()
        if base64_payload is None:
            AzureDevOpsEnterpriseOrchestrator.log().warning("Authorization header is not in the correct form, rejecting.")
            return False

        sent_secret = base64.b64decode(base64_payload).decode("utf-8").split(":")[-1:].pop()
        return sent_secret == shared_secret

    def _repo_clone_url(self, cloner) -> str:
        return self.__clone_urls[cloner.select_protocol_from_supported(self.__clone_urls.keys())]

    async def __get_protected_branches_from_policies(self, scm_service : SCMService):
        query = {}
        branches = []
        prefix_branches = []

        while True:
            resp = await scm_service.exec("GET", f"/{self.__collection}/{self.__repo_key}/_apis/policy/configurations", query)

            policies = self.__policy_scope_query.find(json_on_ok(resp))

            for p in policies:
                if 'refName' in p.value.keys() and p.value['repositoryId'] == self.__repo_id:
                    branches.append(AzureDevOpsEnterpriseOrchestrator.normalize_branch_name(p.value['refName']))

                    # Wildcard matches means there may be more branches that have a policy applied.
                    if p.value['matchKind'] == "Prefix":
                        prefix_branches.append(re.escape(AzureDevOpsEnterpriseOrchestrator.normalize_branch_name(p.value['refName'])))


            if 'x-ms-continuationtoken' in resp.headers.keys():
                query['continuationToken'] = resp.headers['x-ms-continuationtoken']
            else:
                break
    

        # If any of the policies indicated that the ref was a prefix,
        # load the branches and find the matches.
        if len(prefix_branches) > 0:
            query = {}

            match_check = re.compile("|".join(prefix_branches))

            while True:
                resp = await scm_service.exec("GET", f"/{self.__collection}/{self.__repo_key}/_apis/git/repositories/{self.__repo_id}/refs", query)
                
                ref_names = set([AzureDevOpsEnterpriseOrchestrator.normalize_branch_name(ref.value) for ref in self.__branch_names_query.find(json_on_ok(resp))])

                for branch in ref_names:
                    if match_check.match(branch):
                        branches.append(branch)

                if 'x-ms-continuationtoken' in resp.headers.keys():
                    query['continuationToken'] = resp.headers['x-ms-continuationtoken']
                else:
                    break

        return list(set(branches))

    async def _get_protected_branches(self, scm_service : SCMService):
        return self.__default_branches + await self.__get_protected_branches_from_policies(scm_service)

    async def _get_target_branch_and_hash(self):
        return self.__target_branch, self.__target_hash
    
    async def _get_source_branch_and_hash(self) -> tuple:
        return self.__source_branch, self.__source_hash

    async def get_default_cxone_project_name(self) -> str:
        p = CloneUrlParser("azure", self.__remote_url)
        return AzureDevOpsProjectNaming.create_project_name(p.org, self._repo_project_key, self._repo_name)

    async def __is_pr_draft(self) -> bool:
        return bool(AzureDevOpsEnterpriseOrchestrator.__pr_draft_query.find(self.event_context.message)[0].value)

    def __populate_common_push_data(self):
        self.__source_branch = self.__target_branch = AbstractOrchestrator.normalize_branch_name(
            [x.value for x in list(self.__push_target_branch_query.find(self.event_context.message))][0])
        self.__source_hash = self.__target_hash = [x.value for x in list(self.__push_target_hash_query.find(self.event_context.message))][0]

    async def _execute_delegated_push_scan_workflow(self, services : CxOneFlowServices, scan_id : str):
        self.__populate_common_push_data()
        return await AbstractOrchestrator._execute_delegated_push_scan_workflow(self, services, scan_id)

    async def _execute_push_scan_workflow(self, services : CxOneFlowServices, scan_tags : Dict[str, str]=None):
        self.__populate_common_push_data()
        return await AbstractOrchestrator._execute_push_scan_workflow(self, services, scan_tags)

    def __populate_common_pr_data(self):
        self.__source_branch = AbstractOrchestrator.normalize_branch_name([x.value for x in list(self.__pr_frombranch_query.find(self.event_context.message))][0])
        self.__target_branch = AbstractOrchestrator.normalize_branch_name([x.value for x in list(self.__pr_tobranch_query.find(self.event_context.message))][0])
        self.__source_hash = [x.value for x in list(self.__pr_fromhash_query.find(self.event_context.message))][0]
        self.__target_hash = [x.value for x in list(self.__pr_tohash_query.find(self.event_context.message))][0]
        self.__pr_id = str([x.value for x in list(self.__pr_id_query.find(self.event_context.message))][0])

        statuses = list(set([AzureDevOpsEnterpriseOrchestrator.__pr_status_map[x.value] 
                             for x in AzureDevOpsEnterpriseOrchestrator.__pr_reviewer_status_query.find(self.event_context.message)]))

        if not len(statuses) > 0:
            self.__pr_status = "NO_REVIEWERS"
        else:
            self.__pr_status = "/".join(statuses)

        self.__pr_state = AzureDevOpsEnterpriseOrchestrator.__pr_state_query.find(self.event_context.message)[0].value

    async def _execute_delegated_pr_scan_workflow(self, services : CxOneFlowServices, scan_id : str):
        self.__populate_common_pr_data()
        return await AbstractOrchestrator._execute_delegated_pr_scan_workflow(self, services, scan_id)

    async def _execute_pr_scan_workflow(self, services : CxOneFlowServices, scan_tags : Dict[str, str]=None) -> ScanInspector:
        if await self.__is_pr_draft():
            AzureDevOpsEnterpriseOrchestrator.log().info(f"Skipping draft PR {AzureDevOpsEnterpriseOrchestrator.__pr_self_link_query.find(self.event_context.message)[0].value}")
            return

        self.__populate_common_pr_data()

        existing_scans = await services.cxone.find_pr_scans(await services.naming.get_project_name
                                                            (await self.get_default_cxone_project_name(), self.event_context), 
                                                            self.__pr_id, self.__source_hash)

        if len(existing_scans) > 0:
            # This is a scan tag update, not a scan.
            return await AbstractOrchestrator._execute_pr_tag_update_workflow(self, services)
        else:
            repo_details = await services.scm.exec("GET", f"{self.__collection}/{self._repo_project_key}/_apis/git/repositories/{self.__repository_id}")

            if not repo_details.ok:
                AzureDevOpsEnterpriseOrchestrator.log().error(f"Response [{repo_details.status_code}] to request for repository details, event handling aborted.")
                return

            self.__default_branches = [AbstractOrchestrator.normalize_branch_name(repo_details.json()['defaultBranch'])]
            
            return await AbstractOrchestrator._execute_pr_scan_workflow(self, services, scan_tags)


    
    @property
    def __repository_id(self) -> str:
        return [x.value for x in list(self.__repository_id_query.find(self.event_context.message))][0]


    @property
    def _pr_id(self) -> str:
        return self.__pr_id

    @property
    def _pr_status(self) -> str:
        return self.__pr_status

    @property
    def _pr_state(self) -> str:
        return self.__pr_state


    __pr_status_map = {
        -10 : "REJECTED",
        -5 : "WAIT_AUTHOR",
        0 : "NO_REVIEW",
        5 : "APPROVED_COMMENTS",
        10 : "APPROVED"
    }

    __workflow_map = {
        "git.push" : _execute_push_scan_workflow,
        "git.pullrequest.created" : _execute_pr_scan_workflow,
        "git.pullrequest.updated" : _execute_pr_scan_workflow
    }

    __delegate_scan_handler_map = {
        "git.push" : _execute_delegated_push_scan_workflow,
        "git.pullrequest.created" : _execute_delegated_pr_scan_workflow,
        "git.pullrequest.updated" : _execute_delegated_pr_scan_workflow
    }