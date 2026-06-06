from flask import Flask, render_template, jsonify, request
from datetime import datetime
import json, os

app = Flask(__name__)

# Simple in-memory storage for now
jobs = [
    {"id": "SW-001", "client": "Residencia Belle Vue", "type": "CIPP Pipe Lining", "date": "2026-06-02", "status": "In Progress", "technician": "Husband", "notes": ""},
    {"id": "SW-002", "client": "Grand Baie Hotel", "type": "Pipe Inspection", "date": "2026-06-01", "status": "Quoted", "technician": "Husband", "notes": ""},
    {"id": "SW-003", "client": "Tamarin Villas", "type": "Emergency Repair", "date": "2026-05-31", "status": "Open", "technician": "Worker", "notes": ""},
]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    return jsonify(jobs)

@app.route('/api/jobs', methods=['POST'])
def create_job():
    data = request.json
    job = {
        "id": f"SW-{str(len(jobs)+1).zfill(3)}",
        "client": data.get("client"),
        "type": data.get("type"),
        "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
        "status": "Open",
        "technician": data.get("technician", "Husband"),
        "notes": data.get("notes", "")
    }
    jobs.append(job)
    return jsonify(job), 201

if __name__ == '__main__':
    app.run(debug=True)
