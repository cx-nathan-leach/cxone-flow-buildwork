import aio_pika
from .base_workflow import AbstractAsyncWorkflow
from .messaging import DelegatedScanMessage, DelegatedScanDetails, DelegatedScanResultMessage
from typing import Dict

class AbstractResolverWorkflow(AbstractAsyncWorkflow):

    @property
    def capture_logs(self) -> bool:
        raise NotImplementedError("emit_logs")

    @property
    def is_enabled(self) -> bool:
        raise NotImplementedError("is_enabled")
    
    def get_signature(self, details : DelegatedScanDetails) -> bytearray:
        raise NotImplementedError("get_signature")

    def validate_signature(self, signature : bytearray, payload : bytearray) -> bool:
        raise NotImplementedError("validate_signature")
    
    async def deliver_delegated_scan_outcome(self, mq_client : aio_pika.abc.AbstractRobustConnection, 
                                       route_key : str, msg : DelegatedScanResultMessage, exchange : str) -> bool:
        raise NotImplementedError("deliver_delegated_scan_outcome")

    async def delegated_scan_kickoff(self, mq_client : aio_pika.abc.AbstractRobustConnection, route_key : str, msg : DelegatedScanMessage, exchange : str) -> bool:
        raise NotImplementedError("delegated_scan_kickoff")

    async def delegated_scan_resubmit(self, mq_client : aio_pika.abc.AbstractRobustConnection, route_key : str, msg : DelegatedScanMessage, exchange : str,
                                     retries : int) -> bool:
        raise NotImplementedError("delegated_scan_resubmit")

    async def get_delegated_scan_resubmit_count(self, mq_client : aio_pika.abc.AbstractRobustConnection, msg : aio_pika.abc.AbstractIncomingMessage, headers : Dict) -> int:
        raise NotImplementedError("get_delegated_scan_resubmit_count")
