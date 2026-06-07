from flask import Flask, render_template, jsonify, request
from datetime import datetime
import cloudinary
import cloudinary.uploader
import os

app = Flask(__name__)

# Cloudinary config
cloudinary.config(
    cloud_name = "dfonq8k86",
    api_key = "428797737134981",
    api_secret = "tNUZMw-xBME2nYKL5jwABqu9wzU"
)

# In-memory storage
jobs = [
    {"id": "SW-001", "client": "Residencia Belle Vue", "type": "CIPP Pipe Lining", "date": "2026-06-02", "status": "In Progress", "technician": "Husband", "notes": "", "photos": []},
    {"id": "SW-002", "client": "Grand Baie Hotel", "type": "Pipe Inspection", "date": "2026-06-01", "status": "Quoted", "technician": "Husband", "notes": "", "photos": []},
    {"id": "SW-003", "client": "Tamarin Villas", "type": "Emergency Repair", "date": "2026-05-31", "status": "Open", "technician": "Worker", "notes": "", "photos": []},
]

@app.route('/')
def index():
    return render_template('simpliwater_final.html')

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
        "notes": data.get("notes", ""),
        "photos": []
    }
    jobs.append(job)
    return jsonify(job), 201

@app.route('/api/upload', methods=['POST'])
def upload_photo():
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['file']
    job_id = request.form.get('job_id', 'general')
    result = cloudinary.uploader.upload(
        file,
        folder=f"simpliwater/{job_id}",
        resource_type="auto"
    )
    return jsonify({
        "url": result['secure_url'],
        "public_id": result['public_id']
    })

if __name__ == '__main__':
    app.run(debug=True)
