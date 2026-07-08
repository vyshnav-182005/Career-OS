import os
import glob

replacements = {
    "services.config": "backend.config",
    "services.resume_parsing.agent": "backend.agents.resume_parsing_agent",
    "services.resume_optimization.agent": "backend.agents.resume_optimization_agent",
    "services.resume_parsing.models": "backend.models.resume",
    "services.resume_parsing.profile_models": "backend.models.profile",
    "services.resume_optimization.schemas": "backend.models.schemas",
    "services.orchestrator.schemas": "backend.models.schemas",
    "services.resume_parsing.supabase_client": "backend.db.supabase_client",
    "services.auth.router": "backend.routers.auth",
    "services.resume_management.router": "backend.routers.resume_management",
    "services.user_profile.router": "backend.routers.user_profile",
    "services.jobs.router": "backend.routers.jobs",
    "services.applications.router": "backend.routers.applications",
    "services.resume_parsing.router": "backend.routers.resume_parsing",
    "services.resume_optimization.router": "backend.routers.resume_optimization",
    "services.orchestrator.router": "backend.routers.workflows",
    "services.resume_parsing.parser": "backend.services.resume_parser",
    "services.resume_parsing.service": "backend.services.resume_parser",
    "services.resume_optimization.service": "backend.services.resume_optimizer",
    "services.resume_optimization.renderer": "backend.services.resume_renderer",
    "services.orchestrator.service": "backend.services.workflow_orchestrator",
}

def update_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

if __name__ == "__main__":
    for filepath in glob.glob('c:/Academics/project/Career-OS/backend/**/*.py', recursive=True):
        update_file(filepath)
