import sys

def normalize_name(n: str) -> str:
    return "".join(c.lower() for c in n if c.isalnum())

projects = [
    {"name": "Augmented Evaluation System"},
    {"name": "PrisMap"},
    {"name": "WhistleBox"},
    {"name": "Student Companion"},
]

repos = [
    {"name": "student_companion", "html_url": "https://github.com/v/student_companion"},
    {"name": "Augmented_Evaluation_System", "html_url": "https://github.com/v/AES"},
    {"name": "PrisMap", "html_url": "https://github.com/v/PrisMap"},
    {"name": "WhistleBox", "html_url": "https://github.com/v/WhistleBox"},
    {"name": "LeetCode_Py", "html_url": "https://github.com/v/LeetCode_Py"}
]

for repo in repos:
    name = repo.get("name", "Unknown Repository")
    repo_url = repo.get("html_url")
    
    existing_project = None
    for p in projects:
        if p.get("url") == repo_url or normalize_name(p.get("name", "")) == normalize_name(name):
            existing_project = p
            break
    
    if existing_project:
        if not existing_project.get("url") and repo_url:
            existing_project["url"] = repo_url
        continue
        
    projects.append({
        "name": name,
        "url": repo_url
    })

for p in projects:
    print(p)
