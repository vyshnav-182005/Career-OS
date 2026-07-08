import os
import glob

replacements = {
    "@/components/HeroSection": "@/components/landing/HeroSection",
    "@/components/FeaturesSection": "@/components/landing/FeaturesSection",
    "@/components/HowItWorksSection": "@/components/landing/HowItWorksSection",
    "@/components/Footer": "@/components/landing/Footer",
    "@/components/ProfileView": "@/components/dashboard/ProfileView",
    "@/components/ResumeUploader": "@/components/dashboard/ResumeUploader",
    "@/components/ResumeOptimizer": "@/components/dashboard/ResumeOptimizer",
    "@/components/Navbar": "@/components/shared/Navbar",
    "@/components/ThemeProvider": "@/components/shared/ThemeProvider",
    "@/components/ThemeToggle": "@/components/shared/ThemeToggle",
    # also update the import of their own css modules
    "./HeroSection.module.css": "./HeroSection.module.css", # Wait, inside the component, it's the same dir. No need to update css imports inside components.
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
    for filepath in glob.glob('c:/Academics/project/Career-OS/frontend/**/*.ts*', recursive=True):
        if 'node_modules' not in filepath and '.next' not in filepath:
            update_file(filepath)
