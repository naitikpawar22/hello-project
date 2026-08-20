# ExamForge completion checklist

All files below are generated and included in the final package.

- [x] `run.py`
- [x] `requirements.txt`
- [x] `README.md`
- [x] `.env.example`
- [x] `.gitignore`
- [x] `instance/examforge.db`
- [x] `uploads/.gitkeep`
- [x] Authentication: admin bootstrap, login, logout, session, password hashing
- [x] Teacher authentication/creator-scoped authorization
- [x] Dashboard APIs and dark responsive UI
- [x] Student CRUD/status/search/CSV import
- [x] Question-bank imports: PDF, XML, HTML, DOCX, XLSX, XLSM, CSV
- [x] MCQ/MSQ normalization and exact evaluation
- [x] Normal exam builder
- [x] Blank exam builder
- [x] Scheduling with timezone handling and Asia/Kolkata default
- [x] Secure invitation tokens and invitation states
- [x] SMTP email job queue with disabled fallback when SMTP is absent
- [x] Student exam UI and server-side attempt timing
- [x] Browser security event logging with explicit non-authoritative client-side design
- [x] Automatic submission/evaluation/result creation
- [x] Topic performance and question review
- [x] ReportLab PDF result card
- [x] Audit logging
- [x] JSON API error handling
- [x] Tests covering auth, protected endpoints, CSV import, MCQ/MSQ scoring
- [x] Example student and question CSV files
- [x] Compile-time validation of all Python source files
- [x] Local import/reference inventory checked against generated files

## Validation limitation

`pytest` and a real Flask boot could not be executed inside the generation environment because Python dependencies were not preinstalled and the environment could not reach the package index. The source tree was compile-checked successfully, and the SQLite schema was created successfully from the generated schema.
