from typing import List, Dict
from .resolver_opts import ResolverOpts
import subprocess, logging, asyncio, tempfile, os, stat
from .exceptions import ResolverAgentException

class AbstractExecutionContext:
    def __init__(self, workpath: str):
        
        if workpath is not None:
            self.__workpath = workpath.rstrip("/") + "/"
        else:
            self.__workpath = None

        self.__work_root = None

    @classmethod
    def log(clazz):
        return logging.getLogger(clazz.__name__)

    @property
    def work_root(self) -> tempfile.TemporaryDirectory:
        if self.__work_root is None:
            raise ResolverAgentException("Not executing in 'with' scope.")

        return self.__work_root
    
    @work_root.setter
    def work_root(self, value):
        self.__work_root = value

    @property
    def home(self):
        return self.__workpath

    @property
    def clone_directory(self):
        return "clone"

    @property
    def clone_path(self) -> str:
        return self.work_root.name.rstrip("/") + "/" + self.clone_directory

    @property
    def execution_clone_path(self) -> str:
        return self.clone_path

    @property
    def can_execute(self):
        raise NotImplementedError("can_execute")

    async def __aenter__(self):
        self.__work_root = tempfile.TemporaryDirectory(
            delete=False, prefix=self.__workpath
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.log().debug(f"Cleanup: {self.__work_root}")
        self.__work_root.cleanup()
        self.__work_root = None


class ResolverExecutionContext(AbstractExecutionContext):

    _reqd_permissions = stat.S_IRUSR + stat.S_IWUSR + stat.S_IXUSR + stat.S_IRGRP + stat.S_IWGRP + stat.S_IXGRP

    def __init__(self, workpath: str, opts: ResolverOpts):
        super().__init__(workpath)
        self.__opts = opts

    @property
    def resolver_result_directory(self):
        return "resolver"

    @property
    def _resolver_loc(self) -> str:
        return self.work_root.name.rstrip("/") + "/" + self.resolver_result_directory

    @property
    def container_result_directory(self):
        return "container"

    @property
    def _container_loc(self) -> str:
        return self.work_root.name.rstrip("/") + "/" + self.container_result_directory

    @property
    def resolver_result_filename(self) -> str:
        return "resolver.json"

    @property
    def container_result_filename(self) -> str:
        return "container.json"

    @property
    def result_resolver_out_file_path(self) -> str:
        return self._resolver_loc + "/" + self.resolver_result_filename

    @property
    def execution_resolver_out_file_path(self) -> str:
        return self.result_resolver_out_file_path

    @property
    def result_container_out_file_path(self) -> str:
        return self._container_loc + "/" + self.container_result_filename

    @property
    def execution_container_out_file_path(self) -> str:
        return self.result_container_out_file_path

    @property
    def can_execute(self):
        return not self._get_resolver_exec_cmd() == None

    def _get_resolver_exec_cmd(self) -> List[str]:
        raise NotImplementedError("_get_resolver_exec_cmd")

    async def execute_resolver(
        self, project_name: str, exclusions: str
    ) -> subprocess.CompletedProcess:
        cmd = self._get_resolver_exec_cmd()

        def merge_exclusions(x: str):
            return f"{x},{exclusions}"

        resolver_opts = self.__opts.as_args(
            {"e": merge_exclusions, "excludes": merge_exclusions}
        )

        if self.__opts is not None and not self.__opts.has_one_of(["excludes", "e"]):
            exclude_opts = ["--excludes", exclusions]
        else:
            exclude_opts = []

        exec_opts = (
            ["offline"]
            + resolver_opts
            + exclude_opts
            + [
                "--logs-path",
                self.work_root.name,
                "--scan-path",
                self.execution_clone_path,
                "--containers-result-path",
                self.execution_container_out_file_path,
                "--resolver-result-path",
                self.execution_resolver_out_file_path,
                "--project-name",
                project_name,
            ]
        )

        self.log().debug(f"Running resolver: {cmd + exec_opts}")

        try:
            resolver_exec_result = await ResolverRunner.execute_cmd_async(cmd + exec_opts, {"HOME" : self.home})
        except subprocess.CalledProcessError as cpex:
            ResolverExecutionContext.log().exception(cpex)
            resolver_exec_result = subprocess.CompletedProcess(cpex.cmd, cpex.returncode, cpex.stdout, cpex.stderr)

        self.log().debug(f"Resolver finished: {resolver_exec_result}")

        return resolver_exec_result

    async def __aenter__(self):
        await super().__aenter__()

        os.chmod(self.work_root.name, ResolverExecutionContext._reqd_permissions)

        os.mkdir(self.clone_path)
        os.chmod(self.clone_path, ResolverExecutionContext._reqd_permissions)

        os.mkdir(self._resolver_loc)
        os.chmod(self._resolver_loc, ResolverExecutionContext._reqd_permissions)

        os.mkdir(self._container_loc)
        os.chmod(self._container_loc, ResolverExecutionContext._reqd_permissions)

        return self

class AbstractRunner:

    @classmethod
    def log(clazz):
        return logging.getLogger(clazz.__name__)

    def __init__(self, workpath: str):
        if workpath is not None:
            self.__workpath = workpath.rstrip("/") + "/"
        else:
            self.__workpath = None

    @property
    def home(self):
        return self.__workpath

    @property
    def work_path(self) -> str:
        return self.__workpath

    @staticmethod
    async def execute_cmd_async(
        args: List[str], env: Dict[str, str] = None
    ) -> subprocess.CompletedProcess:
        return await asyncio.to_thread(
            subprocess.run,
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
            env=env,
        )

    @staticmethod
    def execute_cmd(
        args: List[str], env: Dict[str, str] = None
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, env=env
        )

    async def executor(self):
        raise NotImplementedError("executor")


class ResolverRunner(AbstractRunner):
    def __init__(self, workpath: str, opts: ResolverOpts):
        super().__init__(workpath)
        self.__opts = opts

    @property
    def resolver_opts(self) -> ResolverOpts:
        return self.__opts

