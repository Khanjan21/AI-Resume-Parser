"""Generate sample resume files for manual testing and demos.

Writes .txt and .docx samples (plus one deliberately invalid file) into
`backend/sample_data/`. Useful from Day 1 smoke tests through Day 7 demos.

Usage:  python scripts/make_sample_resumes.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "sample_data"

SAMPLES: dict[str, str] = {
    "rahul_sharma_ai_engineer.txt": """RAHUL SHARMA
AI Engineer | Bengaluru, India
rahul.sharma@example.com | +91 98765 43210
linkedin.com/in/rahulsharma-ai | github.com/rahulsharma

SUMMARY
AI Engineer with 4 years of experience building production LLM applications.
Shipped retrieval-augmented generation systems serving 2M+ monthly queries with
p95 latency under 800ms. Strong background in Python, PyTorch and vector search.

SKILLS
Languages: Python, SQL, TypeScript
AI/ML: Large Language Models, Prompt Engineering, RAG, Embeddings, Fine-tuning,
       LoRA, PyTorch, Hugging Face Transformers, Model Evaluation
Infrastructure: FastAPI, Docker, Kubernetes, AWS, PostgreSQL, Redis
Vector Search: FAISS, Qdrant, Pinecone, LangChain, LlamaIndex

EXPERIENCE
Senior AI Engineer — Nexora Labs (2023 - Present)
- Designed a RAG pipeline over 4M internal documents using BGE embeddings and
  Qdrant, lifting answer relevance from 0.61 to 0.84 NDCG@10.
- Built an offline evaluation harness (precision, recall, NDCG@K) that gated
  every prompt change before release.
- Cut inference cost 38% through prompt compression and semantic caching.

AI Engineer — Datastack Systems (2021 - 2023)
- Built document-extraction services with FastAPI and Docker on AWS.
- Fine-tuned transformer models for domain classification (F1 0.91).

EDUCATION
B.Tech in Computer Science, VIT Vellore (2017 - 2021)
""",
    "amit_verma_ml_engineer.txt": """AMIT VERMA
Machine Learning Engineer | Pune, India
amit.verma@example.com | +91 90123 45678

SUMMARY
ML Engineer with 3 years of experience productionising models. Owns pipelines
end to end: feature engineering, training, deployment and drift monitoring.

SKILLS
Python, Machine Learning, Scikit-learn, Pandas, NumPy, XGBoost, PyTorch,
MLflow, Airflow, Docker, Kubernetes, SQL, AWS SageMaker, Model Monitoring, CI/CD

EXPERIENCE
Machine Learning Engineer — FinEdge Analytics (2022 - Present)
- Built a churn prediction model (AUC 0.87) served to 400k users daily.
- Automated retraining with Airflow; reduced manual effort by 12 hours/week.
- Instrumented drift detection that caught a feature-skew incident within 2 hours.

Data Analyst — FinEdge Analytics (2021 - 2022)
- Built SQL reporting pipelines and executive dashboards.

EDUCATION
M.Sc. in Data Science, Symbiosis Pune (2019 - 2021)
B.Sc. in Statistics, Fergusson College (2016 - 2019)
""",
    "priya_nair_fullstack.txt": """PRIYA NAIR
Full Stack Developer | Kochi, India
priya.nair@example.com | +91 88990 11223

SUMMARY
Full stack developer with 5 years building customer-facing products in React
and Node.js. Comfortable owning a feature from Figma handoff to production.

SKILLS
JavaScript, TypeScript, React, Next.js, Redux, Node.js, Express, HTML, CSS,
Tailwind CSS, PostgreSQL, MongoDB, REST API, GraphQL, Docker, AWS, Jest, Git

EXPERIENCE
Senior Full Stack Developer — Brightline Commerce (2022 - Present)
- Rebuilt the checkout flow in Next.js, improving conversion by 11%.
- Designed the order-service REST API and its PostgreSQL schema.
- Introduced Jest and Cypress coverage across critical paths.

Full Stack Developer — Webcraft Solutions (2019 - 2022)
- Delivered 14 client projects across React, Express and MongoDB.

EDUCATION
B.Tech in Information Technology, CUSAT (2015 - 2019)
""",
    "sneha_iyer_business_analyst.txt": """SNEHA IYER
Business Analyst | Mumbai, India
sneha.iyer@example.com | +91 77665 44332

SUMMARY
Business Analyst with 6 years bridging business stakeholders and delivery teams
in banking and insurance. Strong in requirement elicitation and process redesign.

SKILLS
Requirement Gathering, Stakeholder Management, SQL, Excel, Power BI, Tableau,
Agile, Scrum, JIRA, Confluence, Process Mapping, Gap Analysis, User Stories,
BRD, FRD, UAT, Documentation, Communication

EXPERIENCE
Senior Business Analyst — Meridian Insurance (2021 - Present)
- Led requirement gathering for a claims platform used by 1,200 staff.
- Mapped current-state processes and removed 3 redundant approval steps,
  cutting average claim turnaround from 9 days to 5.
- Authored BRDs and user stories; coordinated UAT across 4 business units.

Business Analyst — Kotak Financial Services (2018 - 2021)
- Built Power BI dashboards tracking 18 operational KPIs.

EDUCATION
MBA in Finance, NMIMS Mumbai (2016 - 2018)
B.Com, University of Mumbai (2013 - 2016)
""",
}

# A minimal, structurally valid DOCX (a ZIP with the required OOXML parts).
_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _docx_document(text: str) -> str:
    paragraphs = "".join(
        f"<w:p><w:r><w:t xml:space='preserve'>{line}</w:t></w:r></w:p>"
        for line in text.splitlines()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )


def write_docx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        archive.writestr("_rels/.rels", _DOCX_RELS)
        archive.writestr("word/document.xml", _docx_document(text))


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write_pdf(path: Path, text: str) -> None:
    """Hand-rolled, genuinely valid single-page PDF — no reportlab/fpdf needed.

    Builds the object table sequentially while tracking byte offsets, so the
    xref table it emits is correct rather than approximate. pypdf reads the
    result exactly as it would a real Word/Acrobat export.
    """
    lines = [line for line in text.splitlines() if line.strip()][:55]  # fits one page at 11pt
    content_ops = ["BT", "/F1 11 Tf", "12 TL"]
    y = 740
    for line in lines:
        content_ops.append(f"1 0 0 1 50 {y} Tm ({_escape_pdf_text(line)}) Tj")
        y -= 13
    content_ops.append("ET")
    content_bytes = "\n".join(content_ops).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content_bytes)).encode() + b" >>\nstream\n"
        + content_bytes + b"\nendstream",
    ]

    buf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf += f"{index} 0 obj\n".encode()
        buf += obj
        buf += b"\nendobj\n"

    xref_offset = len(buf)
    count = len(objects) + 1
    buf += f"xref\n0 {count}\n".encode()
    buf += b"0000000000 65535 f \n"
    for offset in offsets:
        buf += f"{offset:010d} 00000 n \n".encode()
    buf += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode()

    path.write_bytes(bytes(buf))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, body in SAMPLES.items():
        (OUT_DIR / filename).write_text(body, encoding="utf-8")

    # One DOCX and one real PDF so the parser has non-plaintext samples too.
    write_docx(OUT_DIR / "rahul_sharma_ai_engineer.docx", SAMPLES["rahul_sharma_ai_engineer.txt"])
    write_pdf(OUT_DIR / "amit_verma_ml_engineer.pdf", SAMPLES["amit_verma_ml_engineer.txt"])

    # A file whose extension lies about its contents — must be rejected.
    (OUT_DIR / "not_really_a.pdf").write_bytes(b"This is plain text pretending to be a PDF.")

    print(f"Wrote {len(SAMPLES) + 3} sample files to {OUT_DIR}")


if __name__ == "__main__":
    main()
