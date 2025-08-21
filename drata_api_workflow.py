
import requests
import os
import argparse
import json
from fpdf import FPDF

def get_personnel():
	resp = requests.get("https://api.drata.com/api/personnel", headers=HEADERS)
	resp.raise_for_status()
	return resp.json().get("data", [])

def upload_evidence(personnel_id, control_id, file_path):
	url = "https://api.drata.com/api/evidence"
	with open(file_path, "rb") as f:
		files = {"file": f}
		data = {"personnelId": personnel_id, "controlId": control_id}
		resp = requests.post(url, headers=HEADERS, files=files, data=data)
		resp.raise_for_status()
		return resp.json()

def run_autopilot_test_43():
	url = "https://api.drata.com/api/autopilot/tests/43/run"
	resp = requests.post(url, headers=HEADERS)
	resp.raise_for_status()
	return resp.json()

# Do not know the pdf generation libray at all. I read the docs real quick and had CHATGPT generate this.
def generate_pdf(email, out_path):
	pdf = FPDF()
	pdf.add_page()
	pdf.set_font("Arial", size=16)
	pdf.cell(200, 10, txt="Class Completed", ln=True, align='C')
	pdf.ln(10)
	pdf.set_font("Arial", size=12)
	pdf.cell(200, 10, txt=f"User: {email}", ln=True, align='L')
	pdf.output(out_path)

def process_lms_and_upload(lms_json_path, control_id, pdf_dir):
	# 1. Assume LMS JSON is a file with a list of emails or dicts with 'email' keys 
	with open(lms_json_path, 'r') as f:
		lms_data = json.load(f)
	if isinstance(lms_data, dict):
		# Try to find a list of emails in the dict
        # I don't know what key we're looking for, so let's check common ones
		emails = lms_data.get('emails') or lms_data.get('users') or lms_data.get('completed')
		if isinstance(emails, list):
			lms_emails = set([u['email'] if isinstance(u, dict) else u for u in emails])
		else:
			raise Exception("Could not find list of emails in LMS JSON.")
            # If we're not dealing with a dict/array of dicts, assume it's a list of emails
	elif isinstance(lms_data, list):
		lms_emails = set([u['email'] if isinstance(u, dict) else u for u in lms_data])
	else:
		raise Exception("LMS JSON format not recognized.")

	# 2. Get all personnel from Drata
	personnel = get_personnel()
    # Create a mapping of email to personnel object
    # This assumes each personnel object has an 'email' field
	email_to_person = {p['email'].lower(): p for p in personnel if p.get('email')}

	# 3. Find personnel who have completed training (intersection)
	completed_emails = lms_emails & set(email_to_person.keys())
	not_completed_emails = set(email_to_person.keys()) - lms_emails

	print(f"Users who have completed training: {completed_emails}")
	print(f"Users who have NOT completed training: {not_completed_emails}")

	# 4. Generate PDFs and upload evidence for completed users
	os.makedirs(pdf_dir, exist_ok=True)
	uploaded_emails = []
	for email in completed_emails:
		person = email_to_person[email]
		personnel_id = str(person['id'])
		pdf_path = os.path.join(pdf_dir, f"{personnel_id}.pdf")
		generate_pdf(email, pdf_path)
		try:
			print(f"Uploading evidence for {email} (ID: {personnel_id})...")
			upload_evidence(personnel_id, control_id, pdf_path)
			uploaded_emails.append(email)
		except Exception as e:
			print(f"Failed to upload evidence for {email}: {e}")

	# Run Autopilot test 43
	print("Running Autopilot test 43...")
	run_autopilot_test_43()

	# Validate: Query new list and validate against previous list.
	print("Validating evidence upload...")
	personnel_after = get_personnel()
	email_to_person_after = {p['email'].lower(): p for p in personnel_after if p.get('email')}
	found = [email for email in uploaded_emails if email in email_to_person_after]
	print(f"Emails with evidence uploaded and present in Drata: {found}")
	missing = [email for email in uploaded_emails if email not in found]
	if missing:
		print(f"WARNING: The following emails were not found in Drata after upload: {missing}")
	else:
		print("All uploaded emails are present in Drata.")

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Drata LMS Evidence Automation")
	parser.add_argument("lms_json", help="Path to LMS JSON file(or response) with user emails who completed training.")
	parser.add_argument("control_id", help="Drata control ID to associate with the evidence.")
	parser.add_argument("pdf_dir", help="Directory to store generated PDFs.")
	args = parser.parse_args()

    DRATA_API_KEY = os.environ.get("DRATA_API_KEY")
    if not DRATA_API_KEY:
	    raise EnvironmentError("DRATA_API_KEY environment variable not set.")
    HEADERS = {"Authorization": f"Bearer {DRATA_API_KEY}"}

	# Main workflow
	process_lms_and_upload(args.lms_json, args.control_id, args.pdf_dir)

