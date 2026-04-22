# Project Context

## What This Project Is
A Streamlit web app that helps GIX program coordinator Dorothy collect and manage 
student purchase requests across multiple purchasing rounds and projects.

## Tech Stack
- Python 3.11+
- Streamlit for the web interface
- SQLite for data storage (via gix_db.py)
- Pandas for data manipulation

## Project Structure
- `app.py` — Main application entry point (UI layer)
- `gix_db.py` — All database logic and queries
- `requirements.txt` — Python dependencies
- `.cursorrules` — Cursor AI configuration

## Development Commands
- Run the app: `streamlit run app.py`
- Install dependencies: `pip install -r requirements.txt`

## Coding Standards
- Follow PEP 8 style guidelines
- Use type hints on all function signatures
- Write Google-style docstrings for all functions
- Handle errors gracefully; never let the app crash on user input
- Never hardcode sensitive data (passwords use st.secrets)

## User Roles
- Students: submit purchase requests and track status
- Coordinator (Dorothy): manage requests, set budgets, update order status

## Important Notes
- This is a course project for TECHIN 510 at UW GIX
- Target users: GIX students and program coordinator
- When making changes, always verify the app still runs with `streamlit run app.py`