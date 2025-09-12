from api_utils import verify_signature
from .base import AbstractOrchestrator
from .kickoff import KickoffOrchestrator
import logging
from config import RouteNotFoundException
from config.server import CxOneFlowConfig
from typing import List, Dict, Tuple, Union
from cxoneflow_kickoff_api import KickoffResponseMsg


class OrchestrationDispatch:
    class NotAuthorizedException(BaseException):...

    @staticmethod
    def log():
        return logging.getLogger("OrchestrationDispatch")
    
    
    @staticmethod
    async def execute(orchestrator : AbstractOrchestrator):

        if orchestrator.is_diagnostic:
            return 204

        try:
            OrchestrationDispatch.log().debug(f"Service lookup: {orchestrator.route_urls}")
            services = CxOneFlowConfig.retrieve_services_by_route(orchestrator.route_urls, orchestrator.config_key)
            if services is None:
                OrchestrationDispatch.log().error(f"No configured services for SCM: {orchestrator.config_key}")
                return

            OrchestrationDispatch.log().debug(f"Service lookup success: {orchestrator.route_urls}")

            if await orchestrator.is_signature_valid(services.scm.shared_secret):
                return await orchestrator.execute(services)
            else:
                OrchestrationDispatch.log().warning(f"Payload signature validation failed, webhook payload ignored.")
        except RouteNotFoundException as ex:
            OrchestrationDispatch.log().warning(f"Event [{orchestrator.event_name}] not handled for SCM [{orchestrator.config_key}]")

    @staticmethod
    async def dispatch_delegated_scan_workflow(orchestrator : AbstractOrchestrator, scan_id : str):
        try:
            OrchestrationDispatch.log().debug(f"Service lookup: {orchestrator.route_urls}")
            services = CxOneFlowConfig.retrieve_services_by_route(orchestrator.route_urls, orchestrator.config_key)
            OrchestrationDispatch.log().debug(f"Service lookup success: {orchestrator.route_urls}")

            return await orchestrator.handle_delegated_scan(services, scan_id)
        except RouteNotFoundException as ex:
            OrchestrationDispatch.log().warning(f"Deferred scan for [{orchestrator.event_name}] not handled for SCM [{orchestrator.config_key}]")

    @staticmethod
    async def execute_kickoff(orchestrator : KickoffOrchestrator) -> bool:
        try:
            OrchestrationDispatch.log().debug(f"Service lookup: {orchestrator.route_urls}")
            services = CxOneFlowConfig.retrieve_services_by_route(orchestrator.route_urls, orchestrator.config_key)
            OrchestrationDispatch.log().debug(f"Service lookup success: {orchestrator.route_urls}")
            
            if not await orchestrator.valid_bearer_token(services.kickoff):
                OrchestrationDispatch.log().error(f"{services.cxone.moniker}: Invalid bearer token sent for kickoff scan with SCM [{orchestrator.config_key}]")
                raise OrchestrationDispatch.NotAuthorizedException()
            
            return await orchestrator.execute(services)

        except RouteNotFoundException as ex:
            OrchestrationDispatch.log().warning(f"Event [{orchestrator.event_name}] not handled for SCM [{orchestrator.config_key}]")
            raise ex
