"""Public bank retrieval and extraction only. No applicant context is accepted."""
from .client import GrafilabClient
from .settings import Settings
from .retrieval import KnowledgeBase

class LoanLLMService:
    def __init__(self,settings=None,client=None,fetcher=None):
        self.settings=settings or Settings.load()
        self.client=client or GrafilabClient(self.settings)
        self.knowledge=KnowledgeBase(self.settings,fetcher)

    def live_bank_context(self,bank_code):
        from .live_policies import LiveBankPolicyService
        return LiveBankPolicyService(self).refresh(bank_code)
