import os
import git
import json
import time
import stat
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from openai import AzureOpenAI
import shutil
from datetime import datetime
import base64
import urllib.parse 
from dotenv import load_dotenv
from dataclasses import dataclass
import re
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading
from queue import Queue

class IssueType:
    """Enumeration of issue types for code review."""
    CRITICAL = "Critical Issue"         # Severe bugs, security issues
    IMPROVEMENT = "Improvement Needed"  # Code quality issues
    BEST_PRACTICE = "Best Practice"    # Style and optimization tips
    SECURITY = "Security Concern"      # Security-specific issues
    PERFORMANCE = "Performance Impact" # Performance-specific issues

@dataclass
class AzureConfig:
    """Azure OpenAI configuration settings."""
    endpoint: str
    api_key: str
    deployment: str
    
    @classmethod
    def from_env(cls) -> 'AzureConfig':
        """Create configuration from environment variables."""
        load_dotenv()  # Load environment variables from .env file
        
        endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is not set")
            
        api_key = os.getenv('AZURE_OPENAI_KEY')
        if not api_key:
            raise ValueError("AZURE_OPENAI_KEY environment variable is not set")
            
        deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT')
        if not deployment:
            raise ValueError("AZURE_OPENAI_DEPLOYMENT environment variable is not set")
            
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment
        )

class GitHandler:
    """Handles Git repository operations for both GitHub and Azure DevOps."""
    
    def __init__(self):
        self.temp_dir = None
        self.repo = None
        self.repo_url = None
        
    def _format_repo_url(self, repo_url: str, repo_type: str, username: Optional[str] = None, password: Optional[str] = None) -> str:
        """Formats repository URL based on the repository type and credentials."""
        self.repo_url = repo_url  # Store the original repo URL
        
        if not repo_url.endswith('.git'):
            repo_url = repo_url + '.git'
            
        if username and password:
            # URL encode the username and password
            encoded_username = urllib.parse.quote(username)
            encoded_password = urllib.parse.quote(password)
            
            if 'dev.azure.com' in repo_url:
                # Handle modern Azure DevOps URLs
                parts = repo_url.split('/')
                org = parts[3]  # Organization
                project = parts[4]  # Project
                repo = parts[-1].replace('.git', '')
                repo_url = f"https://{encoded_username}:{encoded_password}@dev.azure.com/{org}/{project}/_git/{repo}"
            elif 'visualstudio.com' in repo_url:
                # Handle legacy Azure DevOps URLs
                parts = repo_url.split('/')
                org = parts[2].split('.')[0]  # Organization
                project = parts[3]  # Project
                repo = parts[-1].replace('.git', '')
                repo_url = f"https://{encoded_username}:{encoded_password}@{org}.visualstudio.com/{project}/_git/{repo}"
            elif 'github.com' in repo_url:
                # Handle GitHub URLs
                repo_url = repo_url.replace('https://', f'https://{encoded_username}:{encoded_password}@')
                
        return repo_url
        
    def clone_repository(self, repo_url: str, repo_type: str, username: Optional[str] = None, password: Optional[str] = None) -> str:
        """Clones a Git repository and returns the path."""
        try:
            # Create a temporary directory
            self.temp_dir = tempfile.mkdtemp()
            formatted_url = self._format_repo_url(repo_url, repo_type, username, password)
            
            # Set git config to handle long paths on Windows
            git.Git().config("--global", "core.longpaths", "true")
            
            # Clone with progress
            self.repo = git.Repo.clone_from(formatted_url, self.temp_dir, progress=git.RemoteProgress())
            return self.temp_dir
        except Exception as e:
            if self.temp_dir and os.path.exists(self.temp_dir):
                self.cleanup()
            raise Exception(f"Failed to clone repository: {str(e)}")
    
    def get_commit_info(self, file_path: str) -> Dict:
        """Get commit information for a specific file."""
        try:
            if not self.repo:
                return {}
            
            # Convert to relative path within the repository
            rel_path = os.path.relpath(file_path, self.temp_dir)
            
            # Get the commit that last modified the file
            commit = next(self.repo.iter_commits(paths=rel_path, max_count=1))
            
            if not commit:
                return {}
            
            pr_patterns = [
                r"Merge pull request #(\d+)",
                r"(?:^|\s)\(#(\d+)\)",
                r"(?:^|\s)#(\d+)",
                r"PR[:\s-]#?(\d+)",
                r"pull[/-](\d+)",
            ]
            
            # Try to extract PR number from commit message
            pr_number = None
            commit_msg = commit.message.strip()
            
            for pattern in pr_patterns:
                match = re.search(pattern, commit_msg)
                if match:
                    pr_number = match.group(1)
                    break
            
            return {
                'committer_name': commit.committer.name,
                'commit_hash': commit.hexsha,
                'commit_message': commit.message.strip(),
                'commit_date': commit.committed_datetime.isoformat(),
                'pr_number': pr_number,
                'repo_url': self.repo_url  # Include the original repo URL
            }
        except Exception as e:
            print(f"Error getting commit info for {file_path}: {str(e)}")
            return {}
    
    def get_code_files(self, directory: str, max_file_size: int = 1000000) -> List[str]:
        """Returns a list of code file paths in the repository."""
        code_extensions = ['.py', '.js', '.java', '.cpp', '.cs', '.rb', '.go', 
                         '.ts', '.swift', '.kt', '.rs', '.html', '.css', '.ipynb']
        
        code_files = []
        try:
            directory = os.path.abspath(directory)
            for root, _, files in os.walk(directory):
                if '.git' in Path(root).parts:  # Skip .git directory
                    continue
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        file_path = Path(file_path)
                        if file_path.suffix.lower() in code_extensions:
                            if file_path.exists() and file_path.is_file():
                                if file_path.stat().st_size <= max_file_size:
                                    code_files.append(str(file_path))
                    except Exception as e:
                        print(f"Skipping file {file}: {str(e)}")
                        continue
        except Exception as e:
            print(f"Error scanning directory: {str(e)}")
        
        return code_files
    
    def cleanup(self):
        """Cleans up temporary directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                print(f"Error cleaning up temporary directory: {str(e)}")
    
    def _handle_readonly(self, func, path, exc_info):
        """Handles read-only files during cleanup."""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            print(f"Could not remove file {path}: {str(e)}")

class CodeReviewer:
    """Handles code review operations using Azure OpenAI."""
    
    def __init__(self, config: Optional[AzureConfig] = None):
        if config is None:
            config = AzureConfig.from_env()
            
        self.client = AzureOpenAI(
            api_key=config.api_key,
            api_version="2024-02-15-preview",
            azure_endpoint=config.endpoint,
            azure_deployment=config.deployment
        )
        
        self.programming_languages_extensions = {
            'py': 'Python', 'cs': 'C#', 'js': 'JavaScript', 'java': 'Java',
            'cpp': 'C++', 'c': 'C', 'rb': 'Ruby', 'go': 'Go', 'php': 'PHP',
            'ts': 'TypeScript', 'swift': 'Swift', 'kt': 'Kotlin', 'rs': 'Rust',
            'html': 'HTML', 'css': 'CSS', 'sh': 'Shell Script', 'dart': 'Dart',
            'ipynb': 'Python'
        }
        self.max_tokens = 4096
        self.chunk_overlap = 500

    def extract_notebook_code(self, notebook_content: str) -> Tuple[str, List[Dict]]:
        """Extracts code cells from a Jupyter notebook."""
        try:
            notebook = json.loads(notebook_content)
            code_cells = []
            cell_metadata = []
            
            for cell_idx, cell in enumerate(notebook.get('cells', []), 1):
                if cell.get('cell_type') == 'code':
                    source = ''.join(cell.get('source', []))
                    if source.strip():
                        code_cells.append(source)
                        cell_metadata.append({
                            'cell_number': cell_idx,
                            'start_line': len(''.join(code_cells[:-1]).splitlines()) + 1
                        })
            
            combined_code = '\n\n'.join(code_cells)
            return combined_code, cell_metadata
        except json.JSONDecodeError:
            print("Error: Invalid notebook format")
            return "", []
        except Exception as e:
            print(f"Error processing notebook: {str(e)}")
            return "", []

    def detect_language(self, file_path: str) -> str:
        """Detects the programming language based on the file extension."""
        extension = os.path.splitext(file_path)[1].lstrip('.')
        return self.programming_languages_extensions.get(extension, 'Unknown')

    def split_code_into_chunks(self, code: str, max_chunk_size: int = 2000) -> List[Tuple[str, int]]:
        """Splits code into chunks while preserving function/class boundaries."""
        lines = code.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        start_line = 1

        for line in lines:
            line_size = len(line)
            if current_size + line_size > max_chunk_size and current_chunk:
                chunks.append(('\n'.join(current_chunk), start_line))
                start_line += len(current_chunk)
                current_chunk = []
                current_size = 0
            current_chunk.append(line)
            current_size += line_size

        if current_chunk:
            chunks.append(('\n'.join(current_chunk), start_line))

        return chunks

    def _get_ai_code_review(self, code: str, language: str, start_line: int = 1, commit_info: Dict = None) -> List[Dict]:
        """Sends the code to Azure OpenAI for review with enhanced issue types and PR information."""
        try:
            prompt = f"""
Please analyze the following {language} code as a senior software developer and provide a thorough review. 
Focus on these categories:
1. CRITICAL ISSUE: Severe bugs, incorrect logic, or major security vulnerabilities
2. IMPROVEMENT NEEDED: Code quality issues that should be addressed
3. BEST PRACTICE: Suggestions for better coding practices and maintainability
4. SECURITY CONCERN: Potential security risks and vulnerabilities
5. PERFORMANCE IMPACT: Performance optimization opportunities
Code to review:
{code}

For each issue found, provide:
- The exact line number
- Clear issue description
- The problematic code snippet
- Detailed explanation of the fix
- Example code showing the fix
- Impact level (high/medium/low)
- Effort estimate (small/medium/large)
**NOTE** Don't skip to generate any of the above Parameter.
Format your response as a single consolidated JSON object with all issues."""

            response = self.client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {"role": "system", "content": "You are a senior software developer providing detailed code reviews."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            try:
                issues = json.loads(response.choices[0].message.content).get('issues', [])
                for issue in issues:
                    issue['line'] = issue.get('line', 1) + start_line - 1
                    if commit_info:
                        issue['commit_info'] = commit_info
                        if commit_info.get('pr_number'):
                            issue['pr_info'] = {
                                'number': commit_info['pr_number'],
                                'url': self._generate_pr_url(commit_info)
                            }
                return issues
            except json.JSONDecodeError:
                return [{
                    'type': IssueType.BEST_PRACTICE,
                    'message': 'General Review',
                    'line': start_line,
                    'code': 'Full file',
                    'original_code_content': code,  # Add the original code here
                    'suggestion': {
                        'text': response.choices[0].message.content,
                        'code': None
                    },
                    'commit_info': commit_info if commit_info else {}
                }]

        except Exception as e:
            print(f"Error during AI review: {str(e)}")
            return [{
                'type': IssueType.CRITICAL,
                'message': f'AI Review Error: {str(e)}',
                'line': start_line,
                'code': 'N/A',
                'suggestion': {
                    'text': 'Manual review recommended',
                    'code': None
                },
                'commit_info': commit_info if commit_info else {}
            }]

    def _generate_pr_url(self, commit_info: Dict) -> str:
        """Generates PR URL based on repository type and PR number."""
        pr_number = commit_info.get('pr_number')
        if not pr_number:
            return None
            
        repo_url = commit_info.get('repo_url', '')
        
        if 'github.com' in repo_url.lower():
            repo_parts = repo_url.split('github.com/')[-1].split('.git')[0]
            return f"https://github.com/{repo_parts}/pull/{pr_number}"
        elif 'dev.azure.com' in repo_url.lower():
            parts = repo_url.split('/')
            org = parts[3]
            project = parts[4]
            return f"https://dev.azure.com/{org}/{project}/_git/pullrequest/{pr_number}"
        return None

    def review_code(self, code_content: str, language: str = "Python", file_path: Optional[str] = None, git_handler: Optional[GitHandler] = None) -> List[Dict]:
        """Reviews the provided code content and returns a consolidated list of issues."""
        try:
            if not code_content.strip():
                return []

            # Get commit info if available
            commit_info = {}
            if file_path and git_handler:
                commit_info = git_handler.get_commit_info(file_path)

            # Review the entire file as one chunk to maintain context
            issues = self._get_ai_code_review(code_content, language, 1, commit_info)
            
            # Store original code content with each issue for reference
            for issue in issues:
                if 'original_code_content' not in issue:
                    issue['original_code_content'] = code_content

            # Deduplicate and sort issues
            unique_issues = self._deduplicate_issues(issues)
            return sorted(unique_issues, key=lambda x: x.get('line', 0))

        except Exception as e:
            return [{
                'type': IssueType.CRITICAL,
                'message': str(e),
                'line': 1,
                'code': 'N/A',
                'suggestion': {
                    'text': 'Check code content',
                    'code': None
                },
                'commit_info': {}
            }]

    def _deduplicate_issues(self, issues: List[Dict]) -> List[Dict]:
        """Removes duplicate issues based on message and line number similarity."""
        unique_issues = []
        seen_issues = set()

        for issue in issues:
            issue_key = (issue.get('line'), issue.get('message', '')[:100])
            if issue_key not in seen_issues:
                seen_issues.add(issue_key)
                unique_issues.append(issue)

        return unique_issues

def review_files_parallel(reviewer: CodeReviewer, files_to_review: List[Dict], git_handler: GitHandler, max_workers: int = 3) -> List[Dict]:
    """Reviews multiple files in parallel using threading."""
    results_queue = Queue()
    review_results = []
    progress_lock = threading.Lock()
    files_completed = 0
    total_files = len(files_to_review)

    def review_file(file_info: Dict) -> Dict:
        """Reviews a single file and updates progress."""
        nonlocal files_completed
        try:
            rel_path = file_info['relative_path']
            abs_path = file_info['absolute_path']
            
            # Get Git information
            commit_info = git_handler.get_commit_info(abs_path)
            
            # Read file content
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    code_content = f.read()
            except UnicodeDecodeError:
                with open(abs_path, 'r', encoding='latin-1') as f:
                    code_content = f.read()
            
            language = reviewer.detect_language(abs_path)
            issues = reviewer.review_code(code_content, language, abs_path, git_handler)
            
            result = {
                'file': rel_path,
                'commit_info': commit_info,
                'issues': issues,
                'original_code_content': code_content,  # Store the original code content
                'issues_count': len(issues),
                'issues_by_type': {
                    IssueType.CRITICAL: len([i for i in issues if i['type'] == IssueType.CRITICAL]),
                    IssueType.IMPROVEMENT: len([i for i in issues if i['type'] == IssueType.IMPROVEMENT]),
                    IssueType.BEST_PRACTICE: len([i for i in issues if i['type'] == IssueType.BEST_PRACTICE]),
                    IssueType.SECURITY: len([i for i in issues if i['type'] == IssueType.SECURITY]),
                    IssueType.PERFORMANCE: len([i for i in issues if i['type'] == IssueType.PERFORMANCE])
                }
            }
            
            with progress_lock:
                nonlocal files_completed
                files_completed += 1
                print(f"\r📊 Progress: {files_completed}/{total_files} files reviewed ({(files_completed/total_files)*100:.1f}%)", end="")
            
            return result
            
        except Exception as e:
            return {
                'file': file_info['relative_path'],
                'error': str(e),
                'issues_count': 0,
                'issues_by_type': {type_name: 0 for type_name in IssueType.__dict__.values() 
                                 if isinstance(type_name, str) and not type_name.startswith('_')}
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(review_file, file_info): file_info 
                         for file_info in files_to_review}
        
        for future in concurrent.futures.as_completed(future_to_file):
            file_info = future_to_file[future]
            try:
                result = future.result()
                review_results.append(result)
            except Exception as e:
                print(f"\n❌ Error reviewing {file_info['relative_path']}: {str(e)}")

    print("\n")  # New line after progress bar
    return review_results

def display_review_results(issues: List[Dict], code_content: str, file_name: str = ""):
    """Displays the review results with enhanced issue types and PR information."""
    print(f"\nReview Results for {Path(file_name).name if file_name else 'Code'}")
    print("=" * 80)
    print()
    
    if not issues:
        print("No issues found in the code!")
        return

    grouped_issues = {issue_type: [] for issue_type in IssueType.__dict__.values() 
                     if isinstance(issue_type, str) and not issue_type.startswith('_')}

    for issue in issues:
        issue_type = issue.get('type', IssueType.BEST_PRACTICE)
        grouped_issues[issue_type].append(issue)

    for issue_type, type_issues in grouped_issues.items():
        if type_issues:
            print(f"\n{issue_type} ({len(type_issues)})")
            print("-" * 40)
            
            for issue in type_issues:
                print(f"\nLine {issue.get('line', 'N/A')}: {issue.get('message', 'No details')}")
                print(f"Impact Level: {issue.get('impact_level', 'N/A')}")
                print(f"Effort Estimate: {issue.get('effort_estimate', 'N/A')}")
                
                if 'commit_info' in issue:
                    print("\nCommit Information:")
                    print(f"Committer: {issue['commit_info'].get('committer_name', 'N/A')}")
                    print(f"Commit Hash: {issue['commit_info'].get('commit_hash', 'N/A')}")
                    print(f"Commit Date: {issue['commit_info'].get('commit_date', 'N/A')}")
                    
                    if 'pr_info' in issue:
                        print("\nPull Request Information:")
                        print(f"PR Number: #{issue['pr_info'].get('number', 'N/A')}")
                        if issue['pr_info'].get('url'):
                            print(f"PR URL: {issue['pr_info']['url']}")
                
                # Check for full file code display with correct case
                if issue.get('code') == 'Full file' and (issue.get('original_code_content') or code_content):
                    print("\nOriginal Code:")
                    print(issue.get('code'))
                    print(issue.get('original_code_content') or code_content)
                elif issue.get('code', 'N/A') != 'N/A':
                    print("\nOriginal Code:")
                    print(issue.get('code'))
                    
                suggestion = issue.get('suggestion', {})
                if isinstance(suggestion, dict):
                    if suggestion.get('text'):
                        print("\nExplanation:")
                        print(suggestion['text'])
                    if suggestion.get('code'):
                        print("\nSuggested Fix:")
                        print(suggestion['code'])
                else:
                    print("\nSuggestion:")
                    print(suggestion)
                
                print("-" * 40)

def review_repository(reviewer: CodeReviewer, repo_url: str, username: Optional[str] = None, password: Optional[str] = None):
    """Enhanced repository review function with parallel processing."""
    git_handler = GitHandler()
    
    try:
        print("\n🔍 Cloning repository...")
        repo_path = git_handler.clone_repository(repo_url, "auto", username, password)
        
        print("📁 Finding code files...")
        code_files = git_handler.get_code_files(repo_path)
        
        if not code_files:
            print("❌ No code files found in the repository.")
            return
        
        print(f"✅ Found {len(code_files)} code files")
        
        repo_path = Path(repo_path)
        display_files = {str(Path(f).relative_to(repo_path)): f for f in code_files}
        
        print("\n📋 Available files for review:")
        for idx, (rel_path, abs_path) in enumerate(display_files.items(), 1):
            commit_info = git_handler.get_commit_info(abs_path)
            last_commit_date = commit_info.get('commit_date', 'N/A')
            committer = commit_info.get('committer_name', 'N/A')
            pr_number = commit_info.get('pr_number', 'N/A')
            print(f"{idx}. {rel_path}")
            print(f"   📝 Last modified by: {committer}")
            print(f"   🕒 Date: {last_commit_date}")
            print(f"   🔄 PR: #{pr_number}" if pr_number != 'N/A' else "   🔄 PR: None")
            if commit_info.get('commit_hash'):
                print(f"   📌 Commit: {commit_info['commit_hash'][:8]}")
        
        print("\n💡 Enter the numbers of files you want to review (comma-separated) or 'all' for all files:")
        selection = input("> ").strip()
        
        files_to_review = []
        if selection.lower() == 'all':
            files_to_review = [{'relative_path': rel_path, 'absolute_path': abs_path} 
                             for rel_path, abs_path in display_files.items()]
        else:
            try:
                indices = [int(idx.strip()) for idx in selection.split(',')]
                file_list = list(display_files.items())
                files_to_review = [{'relative_path': file_list[idx-1][0], 
                                  'absolute_path': file_list[idx-1][1]} 
                                 for idx in indices if 0 < idx <= len(file_list)]
            except (ValueError, IndexError):
                print("❌ Invalid selection. Please enter valid file numbers.")
                return
        
        if files_to_review:
            print(f"\n🚀 Starting parallel review of {len(files_to_review)} files...")
            review_results = review_files_parallel(reviewer, files_to_review, git_handler)
            
            for result in review_results:
                print(f"\n📊 Review Results for {result['file']}")
                print("=" * 80)
                
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                    continue
                
                commit_info = result.get('commit_info', {})
                print("\n📌 File Information:")
                print(f"Last modified by: {commit_info.get('committer_name', 'N/A')}")
                print(f"Commit date: {commit_info.get('commit_date', 'N/A')}")
                print(f"PR number: {commit_info.get('pr_number', 'N/A')}")
                print(f"Commit hash: {commit_info.get('commit_hash', 'N/A')}")
                
                issues = result.get('issues', [])
                original_code = result.get('original_code_content', '')
                display_review_results(issues, original_code, result['file'])
            
            print("\n📊 Repository Review Summary")
            print("=" * 80)
            for result in review_results:
                print(f"\n📁 File: {result['file']}")
                if 'commit_info' in result:
                    commit_info = result['commit_info']
                    print(f"📝 Last modified by: {commit_info.get('committer_name', 'N/A')}")
                    print(f"🕒 Commit date: {commit_info.get('commit_date', 'N/A')}")
                    print(f"🔄 PR: #{commit_info.get('pr_number', 'N/A')}" if commit_info.get('pr_number', 'N/A') != 'N/A' else "🔄 PR: None")
                print(f"📊 Total issues: {result['issues_count']}")
                print("Issues breakdown:")
                for issue_type, count in result['issues_by_type'].items():
                    if count > 0:
                        print(f"- {issue_type}: {count}")
            
            print("\n✅ Repository review completed!")
                    
    except Exception as e:
        print(f"❌ Error processing repository: {str(e)}")
    
    finally:
        git_handler.cleanup()

def main():
    """Main function to run the code reviewer."""
    print("🔍 AI Code Review Assistant")
    print("=" * 50)

    try:
        azure_config = AzureConfig.from_env()
        reviewer = CodeReviewer(azure_config)
        
        print("\n📦 Repository types:")
        print("1. GitHub Public")
        print("2. GitHub Private")
        print("3. Azure DevOps Public")
        print("4. Azure DevOps Private")
        
        repo_type_choice = input("Select repository type (1-4): ")
        repo_types = {
            "1": "GitHub Public",
            "2": "GitHub Private",
            "3": "Azure DevOps Public",
            "4": "Azure DevOps Private"
        }
        repo_type = repo_types.get(repo_type_choice)
        
        if not repo_type:
            print("❌ Invalid repository type selection.")
            return
        
        repo_url = input("\n🔗 Enter repository URL: ")
        
        username = None
        password = None
        
        if "Private" in repo_type:
            if "GitHub" in repo_type:
                print("\n🔐 For GitHub Private repositories:")
                print("1. Use your GitHub username")
                print("2. Use a Personal Access Token with 'repo' scope")
                username = input("GitHub Username: ")
                password = input("GitHub Personal Access Token: ")
            else:  # Azure DevOps
                print("\n🔐 For Azure DevOps repositories:")
                print("1. Use your email as username")
                print("2. Create a Personal Access Token (PAT) with 'Code (Read)' permissions")
                username = input("Azure DevOps Username (email): ")
                password = input("Azure DevOps Personal Access Token: ")
        
        if repo_url:
            if not repo_url.startswith(('http://', 'https://')):
                print("❌ Please enter a valid repository URL")
            else:
                if "Private" in repo_type and (not username or not password):
                    print("❌ Please provide username and personal access token for private repositories.")
                else:
                    review_repository(reviewer, repo_url, username, password)
                    
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print("\n⚙️ Please ensure your .env file contains:")
        print("AZURE_OPENAI_ENDPOINT=<your-endpoint>")
        print("AZURE_OPENAI_KEY=<your-api-key>")
        print("AZURE_OPENAI_DEPLOYMENT=<your-deployment>")
        return
    except Exception as e:
        print(f"❌ Error initializing code reviewer: {e}")
        return
    
