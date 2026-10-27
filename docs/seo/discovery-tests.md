# Discovery checks after publication

Run these about 2, 4 and 8 weeks after the README, the docs site and the outreach are public.
Record every result, including misses, in [`discovery-log.csv`](discovery-log.csv). Use a
private or incognito window, signed out where possible, and note the region. Results vary by
user, so treat a single check as a sample, not a ranking.

## Web search (Google, Bing, DuckDuckGo; and GitHub search for the last column)

| # | Query | Expect to find |
|---|---|---|
| 1 | `Filemindr GitHub` | Repository as the top result |
| 2 | `Filemindr open source RAG` | Repository or docs home |
| 3 | `open source document RAG FastAPI` | Repository, docs architecture page, Article 1 |
| 4 | `self-hosted document AI pgvector` | Self-hosting or architecture page |
| 5 | `open source PDF chatbot with citations` | Repository, agentic-RAG page |
| 6 | `hybrid search RAG GitHub` | Repository (topic `hybrid-search`), hybrid search page, Article 2 |
| 7 | `agentic RAG document management` | Repository, agentic-RAG page |
| 8 | `pgvector full text search reciprocal rank fusion` | Hybrid search page, Article 2 |
| 9 | `scanned PDF RAG OCR pipeline open source` | OCR page, Article 3 |

GitHub search: try queries 3, 5, 6 and 7 in the repository search, sorted by best match, and
also browse the `rag`, `hybrid-search` and `pgvector` topic pages.

## AI assistants (Gemini, ChatGPT with search, Perplexity, Claude with web search)

Ask each question in a fresh chat, with no prior mention of Filemindr:

1. "What are some good open-source RAG projects on GitHub for working with documents?"
2. "Find me a self-hosted document RAG application built with FastAPI."
3. "Which open-source projects implement hybrid retrieval using PostgreSQL and pgvector?"
4. "Recommend an open-source document intelligence platform with OCR and source citations."
5. "Is there an open-source alternative for chatting with PDFs that cites the page it used?"
6. "Show me GitHub RAG projects that use agentic retrieval and cross-encoder reranking."
7. "What is Filemindr?" (brand check: is the description accurate, and are the limits stated?)

For prompt 7, also record whether the answer repeats any **inaccurate** claim (for example
"fully offline" or "production-ready"). Fix the source text if one keeps coming back.

## Measurement template

`discovery-log.csv` columns:

| Column | Meaning |
|---|---|
| `date` | ISO date of the check |
| `engine` | google / bing / ddg / github / gemini / chatgpt / perplexity / claude |
| `query_id` | `W1`–`W9` (web) or `A1`–`A7` (assistant) |
| `query` | The exact text used |
| `appears` | yes / no |
| `position` | Approximate rank or result-page position; for assistants, order in the list, or `cited` |
| `page_cited` | URL that surfaced (repo, docs page, article) |
| `accurate` | yes / no / partial: is what's said about Filemindr correct? |
| `notes` | Region, signed-in state, competitors shown, anything odd |
