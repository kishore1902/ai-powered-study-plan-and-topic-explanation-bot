# GapFinder

GapFinder is a study-planning web app that helps learners identify what to review next. It turns a learner's syllabus, notes, and past papers into a topic map, source-based practice quizzes, progress reports, and a day-by-day revision plan.

The app combines keyword retrieval over a learner's own materials with Groq-hosted language models. Retrieved passages are supplied as context for AI-generated questions and explanations; mastery scores and study schedules are calculated by application code.

## What you can do

- Create an account and keep separate study data for each user.
- Upload PDFs, plain text, or Markdown files, or paste text directly.
- Label materials as a **syllabus**, **notes/textbook**, or **past paper**.
- Extract topics and subtopics from a syllabus.
- Match past-paper questions to topics and find relevant passages in notes.
- Generate multiple-choice and short-answer quizzes from relevant note passages.
- Review answers, explanations, source passages, and a report of weak topics.
- Track quiz scores and topic mastery over time.
- Build and adjust a revision schedule based on the time until an exam and daily study hours.
- Ask questions about uploaded notes and see which passages informed the answer.

## How it works

1. **Add materials.** The server extracts PDF text or accepts text directly, then splits it into searchable passages. Password-protected and scanned image-only PDFs are not supported; scanned documents need OCR first.
2. **Build the topic map.** Groq reads the uploaded syllabus and returns a structured list of topics. The app uses keyword matching to relate past-paper questions and note passages to those topics.
3. **Practice.** For selected topics, the app retrieves matching passages from notes and asks Groq to create questions using those passages. Quiz answers are kept on the server until submission.
4. **Review.** Multiple-choice answers are scored by code. Short answers are graded by Groq against their source passage; if Groq is unavailable, the app uses a basic word-overlap fallback. The app records attempts and summarizes mastery, recent mistakes, and supporting sources.
5. **Plan.** The app prioritizes weaker topics and topics that appear more often in past papers. Code allocates study time and builds the daily schedule; Groq can provide optional study tips.
6. **Ask questions.** The app first searches notes for relevant passages. If none are found, it does not call the model. Otherwise, Groq is instructed to answer from those passages, and citations are checked against the retrieved source IDs.

Retrieval is BM25 keyword search, not vector or semantic search. Model responses can still be imperfect, so use cited passages to verify generated content.

## Project structure

```text
api/index.py       Vercel ASGI entry point
backend/
  auth.py          Password hashing and signed session tokens
  db.py            SQLite/PostgreSQL connection and schema setup
  llm.py           Groq chat-completions client
  logic.py         Deterministic mastery and scheduling calculations
  main.py          FastAPI routes and local static-file serving
  models.py        SQLAlchemy database models
  rag.py           Text chunking and BM25 retrieval
  services.py      Material, quiz, report, and study-plan workflows
public/
  index.html       Sign-in page
  signup.html      Account creation page
  app.html         Study workspace
  app.js           Workspace behavior and API calls
  auth.js          Browser session, settings, and API helpers
  style.css        Shared responsive styles
run.py             Local development server
vercel.json        Vercel function and API rewrite configuration
requirements.txt   Python dependencies
```

## Requirements

- Python 3.10 or later
- A Groq API key for AI-powered features
- PostgreSQL for persistent Vercel deployments; SQLite is used locally

## Run locally

From the project directory, create and activate a virtual environment, install dependencies, and start the app:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). You can create an account or use the seeded demo account:

```text
Email:    demo@gapfinder.app
Password: demo1234
```

The demo account is for trying the app, not for private data. Add your Groq API key under **Settings** to use AI features, then upload your own syllabus and notes. You can also load sample Operating Systems materials from the **Materials** page.

Local data is stored in `gapfinder.db` in the project directory.

## Deploy to Vercel

1. Push the project to a GitHub repository and import it into Vercel.
2. Connect a PostgreSQL database and add its connection string as the `DATABASE_URL` environment variable. The backend also recognizes `POSTGRES_URL` and `POSTGRES_URL_NON_POOLING`.
3. Add a long, random `SECRET_KEY` environment variable. This key is used to sign login tokens; do not use the development fallback in production.
4. Deploy the project. Create or log into an account and enter a Groq API key under **Settings**.

The Vercel function is configured with a 60-second maximum duration. Vercel's local function filesystem is temporary; without a PostgreSQL connection, data may be lost when functions restart. Database tables are created by the application at startup.

## Configuration and data

- **Groq key:** entered in Settings and saved in that browser's local storage. It is sent to the backend with API requests and used for Groq calls; the application does not put it in a server-side environment variable or save it in the database. Do not use a shared or untrusted browser for a personal key.
- **Groq model:** the default is `openai/gpt-oss-120b`. A different model can be entered in Settings if it is available to your Groq account.
- **Database:** locally, `gapfinder.db` is used by default. On Vercel, configure PostgreSQL for persistent accounts, materials, quizzes, and progress.
- **Uploads:** each file is limited to approximately 4 MB to fit within Vercel request limits. The app stores extracted text passages rather than the original uploaded file. The total stored study text per user is limited to about 600,000 characters.
- **Authentication:** passwords are hashed; login sessions are signed tokens that expire after 14 days. Set a stable `SECRET_KEY` in production so tokens remain verifiable across function instances.

## API overview

All application endpoints are under `/api`. Routes that access user data require a bearer session token.

| Area | Routes | Purpose |
|---|---|---|
| Authentication | `POST /auth/signup`, `POST /auth/login` | Create an account or sign in |
| Account | `GET /me`, `DELETE /data` | Read account status or delete the current user's study data |
| Materials | `GET/POST /docs`, `POST /docs/text`, `POST /docs/sample`, `DELETE /docs/{id}` | List, add, sample, and remove materials |
| Topics | `GET /topics`, `POST /topics/build` | View or generate the topic map |
| Quiz | `GET /quiz`, `POST /quiz/generate`, `POST /quiz/submit`, `DELETE /quiz` | Generate, take, submit, or discard a quiz |
| Reports and plan | `GET /gaps`, `GET /progress`, `GET/PUT /plan`, `POST /plan/tips` | View results and manage revision schedule and tips |
| Study assistant | `POST /explain` | Ask a question grounded in retrieved notes |
| Connection check | `POST /groq/test`, `GET /health` | Test Groq access or check API availability |

Interactive API documentation is available at `/docs` while the FastAPI server is running.

## Troubleshooting

- **AI features report a missing key:** enter a valid Groq API key in **Settings** and use **Test connection**.
- **Groq rejects the selected model:** choose a model currently available to your Groq account in **Settings**.
- **An upload contains no readable text:** for a scanned PDF, run OCR and upload a searchable PDF or paste extracted text.
- **A topic has no matching note passages:** check the relevant notes are uploaded as **Notes / textbook**, and try clearer wording in the source material.
- **Data disappears after a Vercel restart:** configure and verify the PostgreSQL `DATABASE_URL`; local files on Vercel are not persistent.
