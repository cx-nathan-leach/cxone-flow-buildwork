from agent.resolver.resolver_runner import ResolverRunner, ResolverExecutionContext
from agent.resolver.resolver_opts import ResolverOpts
from typing import List
from pathlib import Path
import os, subprocess

class ResolverShellExecutionContext(ResolverExecutionContext):
    __resolver_name = "ScaResolver"

    def __init__(self, workpath: str, opts: ResolverOpts, resolver_path: str, runas_user : str):
        super().__init__(workpath, opts)
        self.__resolver_path = resolver_path
        self.__runas = runas_user

    def _get_resolver_exec_cmd(self) -> List[str]:
        if self.__runas is not None:
            runas = ["sudo", "-u", self.__runas, f"HOME={self.home}"]
        else:
            runas = []

        cmd = None

        if self.__resolver_path is not None and (
            os.path.exists(self.__resolver_path)
            and os.path.isfile(self.__resolver_path)
        ):
            cmd = [self.__resolver_path]
        elif os.path.exists(ResolverShellExecutionContext.__resolver_name):
            cmd = [ResolverShellExecutionContext.__resolver_name]
        
        exec_cmd = runas + cmd

        self.log().debug(f"Resolver exec cmd: {exec_cmd}")

        return exec_cmd
    
    async def __recurse_chmod(self, path : Path) -> None:
        # This will chmod the files recursively to ExecutionContext._reqd_permissions
        os.chmod(path, ResolverExecutionContext._reqd_permissions)

        for elem in path.iterdir():
            os.chmod(elem, ResolverExecutionContext._reqd_permissions)

            if elem.is_dir():
                await self.__recurse_chmod(elem)

    async def execute_resolver(
        self, project_name: str, exclusions: str
    ) -> subprocess.CompletedProcess:
        if self.__runas is not None:
            # Some tools, like npm, need to have read/write access to the code
            # for the dependency resolution.  
            await self.__recurse_chmod(Path(self.clone_path))
        
        return await super().execute_resolver(project_name, exclusions)

class ResolverShellRunner(ResolverRunner):

    def __init__(self, workpath: str, opts: ResolverOpts, resolver_path: str, runas_user : str):
        super().__init__(workpath, opts)
        self.__resolver_path = resolver_path
        self.__runas = runas_user

    async def executor(self):
        return ResolverShellExecutionContext(self.work_path, self.resolver_opts, self.__resolver_path, self.__runas)
