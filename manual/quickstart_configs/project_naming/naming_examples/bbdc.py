from api_utils.auth_factories import EventContext
from scm_services import BasicSCMService
import logging

############################################################
#### Project Naming Code Example: BitBucket Data Center ####
############################################################

async def event_project_name_factory(context : EventContext, scm_service : BasicSCMService) -> str:
  # Get an instance of the logger
  log = logging.getLogger(__name__)

  # Output the event context to the debug log
  log.debug(context)

  repo_dict = None
  if 'repository' in context.message.keys():
    log.debug("BitBucket push event")
    repo_dict = context.message['repository']
  elif 'pullRequest' in context.message.keys():
    log.debug("BitBucket pull-request event")
    repo_dict = context.message['pullRequest']['toRef']['repository']

  # Look for the repository element that is included in push/pull-request events
  if repo_dict is not None:
    slug = repo_dict['slug']

    # Check for the project element that has the project key
    if 'project' in repo_dict.keys():
      key = repo_dict['project']['key']
      return f"{key}_{slug}"
    else:
      log.debug("Could not find [repository.project] in the context message.")

  else:
    log.debug("Could not find [repository] in the context message.")

  # Failure causes the default project name to be used
  return None

