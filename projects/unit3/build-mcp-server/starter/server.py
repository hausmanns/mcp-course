#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
"""

import json
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# PR template directory (shared across all modules)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

@mcp.tool()
async def analyze_file_changes(base_branch: str = "main", include_diff: bool = True) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
    """
    try:
        # Get the working directory from MCP context
        context = mcp.get_context()
        roots_result = await context.session.list_roots()
        working_dir = roots_result.roots[0].uri.path if roots_result.roots else "."
        
        # Get list of changed files
        result_files = subprocess.run(
            ["git", "diff", "--name-status", base_branch],
            capture_output=True,
            text=True,
            cwd=working_dir
        )
        
        if result_files.returncode != 0:
            return json.dumps({
                "error": f"Git command failed: {result_files.stderr}",
                "files_changed": [],
                "diff": ""
            })
        
        # Parse changed files
        files_changed = []
        for line in result_files.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 2:
                    status = parts[0]
                    filename = parts[1]
                    files_changed.append({
                        "status": status,
                        "filename": filename
                    })
        
        result = {
            "files_changed": files_changed,
            "total_files": len(files_changed)
        }
        
        # Get diff if requested
        if include_diff and files_changed:
            result_diff = subprocess.run(
                ["git", "diff", base_branch],
                capture_output=True,
                text=True,
                cwd=working_dir
            )
            
            if result_diff.returncode == 0:
                diff_content = result_diff.stdout
                
                # Handle token limit - truncate if too large (approximately 20,000 chars = ~5,000 tokens)
                max_diff_chars = 20000
                if len(diff_content) > max_diff_chars:
                    diff_lines = diff_content.split('\n')
                    truncated_lines = []
                    char_count = 0
                    
                    for line in diff_lines:
                        if char_count + len(line) + 1 > max_diff_chars:
                            break
                        truncated_lines.append(line)
                        char_count += len(line) + 1
                    
                    result["diff"] = '\n'.join(truncated_lines)
                    result["diff_truncated"] = True
                    result["original_diff_size"] = len(diff_content)
                else:
                    result["diff"] = diff_content
                    result["diff_truncated"] = False
            else:
                result["diff"] = ""
                result["diff_error"] = result_diff.stderr
        else:
            result["diff"] = ""
            
        return json.dumps(result)
        
    except Exception as e:
        return json.dumps({
            "error": f"Exception occurred: {str(e)}",
            "files_changed": [],
            "diff": ""
        })


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    try:
        templates = []
        
        # Check if templates directory exists
        if not TEMPLATES_DIR.exists():
            return json.dumps({
                "error": f"Templates directory not found: {TEMPLATES_DIR}",
                "templates": []
            })
        
        # Read all .md files in the templates directory
        for template_file in TEMPLATES_DIR.glob("*.md"):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract template name from filename (remove .md extension)
                template_name = template_file.stem
                
                templates.append({
                    "filename": template_file.name,
                    "name": template_name,
                    "type": template_name,  # bug, feature, docs, etc.
                    "content": content
                })
                
            except Exception as e:
                # If we can't read a specific template, include an error but continue
                templates.append({
                    "filename": template_file.name,
                    "name": template_file.stem,
                    "type": template_file.stem,
                    "error": f"Failed to read template: {str(e)}"
                })
        
        # Sort templates by name for consistent ordering
        templates.sort(key=lambda x: x.get('name', ''))
        
        return json.dumps(templates)
        
    except Exception as e:
        return json.dumps({
            "error": f"Failed to get PR templates: {str(e)}",
            "templates": []
        })


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    try:
        # Define mappings from change types to template files
        template_mappings = {
            "bug": "bug.md",
            "bugfix": "bug.md", 
            "fix": "bug.md",
            "feature": "feature.md",
            "feat": "feature.md",
            "enhancement": "feature.md",
            "docs": "docs.md",
            "documentation": "docs.md",
            "doc": "docs.md",
            "refactor": "refactor.md",
            "refactoring": "refactor.md",
            "test": "test.md",
            "tests": "test.md",
            "testing": "test.md",
            "performance": "performance.md",
            "perf": "performance.md",
            "optimization": "performance.md",
            "security": "security.md",
            "sec": "security.md"
        }
        
        # Normalize the change type to lowercase for matching
        normalized_type = change_type.lower().strip()
        
        # Find the appropriate template
        suggested_template_file = template_mappings.get(normalized_type)
        
        if not suggested_template_file:
            # If no exact match, try to find a partial match
            for key, template_file in template_mappings.items():
                if key in normalized_type or normalized_type in key:
                    suggested_template_file = template_file
                    break
        
        # If still no match, default to feature template
        if not suggested_template_file:
            suggested_template_file = "feature.md"
            fallback_used = True
        else:
            fallback_used = False
        
        # Try to read the suggested template
        template_path = TEMPLATES_DIR / suggested_template_file
        
        if template_path.exists():
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_content = f.read()
                
                result = {
                    "recommended_template": suggested_template_file,
                    "template_type": template_path.stem,
                    "template_content": template_content,
                    "changes_summary": changes_summary,
                    "detected_change_type": change_type,
                    "fallback_used": fallback_used
                }
                
                if fallback_used:
                    result["note"] = f"No specific template found for '{change_type}', defaulting to feature template"
                
                return json.dumps(result)
                
            except Exception as e:
                return json.dumps({
                    "error": f"Failed to read template file {suggested_template_file}: {str(e)}",
                    "recommended_template": suggested_template_file,
                    "template_type": template_path.stem
                })
        else:
            return json.dumps({
                "error": f"Template file not found: {suggested_template_file}",
                "available_templates": list(template_mappings.values()),
                "detected_change_type": change_type
            })
            
    except Exception as e:
        return json.dumps({
            "error": f"Failed to suggest template: {str(e)}",
            "changes_summary": changes_summary,
            "change_type": change_type
        })


if __name__ == "__main__":
    mcp.run()