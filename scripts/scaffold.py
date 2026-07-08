import os

services = ["auth", "resume_management", "user_profile", "jobs", "applications"]
files = ["__init__.py", "router.py", "service.py", "repository.py", "schemas.py"]

for svc in services:
    for f in files:
        filepath = os.path.join(svc, f)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as file:
                if f == "router.py":
                    file.write(f"from fastapi import APIRouter\n\nrouter = APIRouter(prefix='/{svc.replace('_', '-')}', tags=['{svc.replace('_', ' ').title()}'])\n")
                elif f == "__init__.py":
                    file.write("")
                else:
                    file.write(f"# {f} for {svc}\n")
            print(f"Created {filepath}")
