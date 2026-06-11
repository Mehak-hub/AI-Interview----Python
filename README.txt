# InterviewAI - Python Flask Project
# Setup Instructions

## Step 1: Install Python
Make sure Python 3.8+ is installed on your computer.
Check: python --version

## Step 2: Install Flask
Open PowerShell/Terminal in the project folder and run:
pip install flask

## Step 3: Run the App
python app.py

## Step 4: Open in Browser
Go to: http://localhost:5000

## Project Structure
interviewai-python/
├── app.py                  ← Main Python Flask server
├── requirements.txt        ← Python dependencies
├── data/
│   ├── hr_questions.csv    ← 30 HR questions (3 rounds)
│   ├── tech_questions.csv  ← 30 Technical questions (3 rounds)
│   ├── data_questions.csv  ← 30 Data Analytics questions (3 rounds)
│   └── users.json          ← Created automatically when first user signs up
└── templates/
    ├── login.html          ← Login/Signup page
    ├── choose.html         ← Category selection page
    ├── interview.html      ← Main interview page
    ├── result.html         ← Results with green/red tracker
    └── dashboard.html      ← Analytics dashboard

## How the Interview Works
1. Login/Signup
2. Choose category: HR / Technical / Data Analytics
3. Round 1 (5 basic questions) - Need 60%+ to advance
4. Round 2 (5 intermediate questions) - Need 60%+ to advance
5. Round 3 (5 advanced questions)
6. Results page with Wayground-style green/red question tracker
7. Dashboard shows analytics across all sessions

## Scoring System (Pure Python)
- Python checks your answer for keyword matches
- Each question has expected keywords
- Score = keyword match % + length bonus (max 100)
- Pass threshold = 60% per round
- Fail a round = eliminated, shown result immediately
