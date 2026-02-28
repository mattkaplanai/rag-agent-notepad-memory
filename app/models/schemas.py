"""
Data models (schemas) for the refund decision pipeline.
All dataclasses in one place for clean imports.
"""

from dataclasses import dataclass, field


@dataclass
class ClassifierOutput:
    """Structured facts extracted from the user's messy description."""
    case_category: str = ""
    flight_type: str = ""
    flight_duration_hours: float | None = None
    delay_hours: float | None = None
    bag_delay_hours: float | None = None
    ticket_price: float | None = None
    ancillary_fee: float | None = None
    original_class: str = ""
    downgraded_class: str = ""
    original_class_price: float | None = None
    downgraded_class_price: float | None = None
    payment_method: str = ""
    accepted_alternative: bool = False
    alternative_type: str = ""
    passenger_traveled: bool = False
    booking_date: str = ""
    flight_date: str = ""
    airline_name: str = ""
    flight_number: str = ""
    key_facts: list[str] = field(default_factory=list)
    raw_description: str = ""


@dataclass
class JudgeVerdict:
    """The Judge's review of the specialist's decision."""
    approved: bool = True
    issues_found: list[str] = field(default_factory=list)
    corrections: dict = field(default_factory=dict)
    override_decision: str = ""
    override_reasons: list[str] = field(default_factory=list)
    confidence_adjustment: str = ""
    explanation: str = ""


@dataclass
class RetrievedChunk:
    """A single retrieved chunk with metadata for citation tracking."""
    content: str = ""
    source_file: str = ""
    relevance_score: float = 0.0
    retrieval_method: str = ""
    vector_rank: int | None = None
    bm25_rank: int | None = None
    rerank_score: float = 0.0


@dataclass
class RetrievalResult:
    """Complete retrieval result with chunks and diagnostics."""
    chunks: list[RetrievedChunk] = field(default_factory=list)
    query: str = ""
    vector_count: int = 0
    bm25_count: int = 0
    hybrid_count: int = 0
    reranked: bool = False

    @property
    def context_text(self) -> str:
        return "\n\n".join(c.content for c in self.chunks)

    @property
    def citation_summary(self) -> list[dict]:
        seen = set()
        citations = []
        for c in self.chunks:
            if c.source_file not in seen:
                seen.add(c.source_file)
                citations.append({
                    "source": c.source_file,
                    "relevance": round(c.rerank_score or c.relevance_score, 3),
                    "method": c.retrieval_method,
                })
        return citations


@dataclass
class WorkerOutput:
    """Output from a single worker agent."""
    agent_name: str = ""
    result: str = ""
    tools_used: list[str] = field(default_factory=list)


@dataclass
class MultiAgentResult:
    """Combined result from all worker agents."""
    researcher_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Researcher", ""))
    analyst_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Analyst", ""))
    writer_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Writer", ""))
    supervisor_decision: dict = field(default_factory=dict)
    agent_log: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Full pipeline result: classifier + agents + judge."""
    classifier_output: ClassifierOutput = field(default_factory=ClassifierOutput)
    multi_agent_result: MultiAgentResult = field(default_factory=MultiAgentResult)
    judge_verdict: JudgeVerdict = field(default_factory=JudgeVerdict)
    final_decision: dict = field(default_factory=dict)
    pipeline_log: list[str] = field(default_factory=list)
