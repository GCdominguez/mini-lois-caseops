# Portfolio Positioning Notes

## One-line description

Built a local agentic legal workflow assistant prototype using Ollama, Chroma, Streamlit, and SQLite to explore matter-scoped retrieval, source-cited AI answers, structured action proposals, human approval gates, and audit logging.

## Interview explanation

I wanted to understand the PM surface area behind AI workflow tools beyond the marketing layer. So I built a small local prototype that ingests fake legal matter documents, retrieves matter-scoped context, answers questions with citations, proposes structured actions, and writes approved actions back to a mock matter system with an audit log.

The main learning was that the product challenge is not just prompting. The harder problems are scoped context, permissions, action safety, workflow failure states, user trust, and source verification.

## Resume bullet option

- Built a local AI legal workflow assistant prototype with Ollama, Chroma, Streamlit, and SQLite, demonstrating matter-scoped RAG, source-cited answers, structured action proposals, human approval gates, and audit logging.

## PM talking points

- AI actions should be proposed before execution unless the workflow has explicit automation rules.
- Source citations are a product trust mechanism, not just a UX enhancement.
- Workflow builders need testing, versioning, rollback, and job history.
- Retrieval quality needs measurable evaluation, not vibes.
- Legal users need clear boundaries between summarization, operational assistance, and legal advice.
