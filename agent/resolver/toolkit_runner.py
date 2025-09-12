from agent.resolver.resolver_runner import ResolverRunner, ResolverExecutionContext
from agent.resolver.resolver_opts import ResolverOpts
from agent.resolver.exceptions import ResolverAgentException
from typing import List
import os

class ResolverToolkitExecutionContext(ResolverExecutionContext):
  __docker_cmd = ["docker", "run", "-t", "--rm"]

  def __init__(self, workpath : str, opts : ResolverOpts, container_tag : str):
    super().__init__(workpath, opts)
    self.__run_container_tag = container_tag

  @property
  def execution_clone_path(self) -> str:
      return "/sandbox/input_sandbox"

  @property
  def execution_resolver_out_file_path(self) -> str:
      return "/sandbox/output/" +  self.resolver_result_directory + "/" + self.resolver_result_filename

  @property
  def execution_container_out_file_path(self) -> str:
      return "/sandbox/output/" +  self.container_result_directory + "/" + self.container_result_filename

  def _get_resolver_exec_cmd(self) -> List[str]:
    return ResolverToolkitExecutionContext.__docker_cmd + [
      "-v", f"{self.clone_path}:/sandbox/input:ro",
      "-v", f"{self.work_root.name}:/sandbox/output",
      self.__run_container_tag
    ]


class ResolverToolkitRunner(ResolverRunner):

  def __init__(self, workpath : str, opts : ResolverOpts, toolkit_path : str, container_tag : str, inherit_uid : bool, inherit_gid : bool):
    super().__init__(workpath, opts)
    self.__toolkit_path = toolkit_path.rstrip("/") + "/"
    self.__src_container_tag = container_tag
    self.__uid = inherit_uid
    self.__gid = inherit_gid

    ResolverToolkitRunner.__check_cmd_on_path_or_fail("docker")
    ResolverToolkitRunner.__check_cmd_on_path_or_fail("bash")

    self.__run_container_tag = self.__get_build_container_tag()

  @staticmethod
  def __check_cmd_on_path_or_fail(cmd_name : str):
    if not os.path.exists(cmd_name) and os.path.isfile(cmd_name):
      raise ResolverAgentException(f"The required '{cmd_name}' command was not found on the path.")

  
  def __get_build_container_tag(self) -> str:
    build_args = [f"{self.__toolkit_path}autobuild.sh", "-t", self.__src_container_tag, "-d", self.__toolkit_path]

    if self.__uid:
      build_args.append("-u")

    if self.__gid:
      build_args.append("-g")

    self.log().debug(f"Pre-building container: f{build_args}")

    resolver_tag = (ResolverRunner.execute_cmd(build_args, {"HOME" : self.home})).stdout.decode().rstrip("\n")

    self.log().debug(f"Toolkit: {self.__src_container_tag} -> {resolver_tag}")

    return resolver_tag


  async def executor(self):
      return ResolverToolkitExecutionContext(self.work_path, self.resolver_opts, self.__run_container_tag)


