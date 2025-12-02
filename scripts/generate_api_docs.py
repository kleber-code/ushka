import ast
import os
import shutil


def generate_doc_from_file(filepath):
    with open(filepath, "r") as source:
        tree = ast.parse(source.read())

    docstrings = {}

    # Module docstring
    module_docstring = ast.get_docstring(tree)
    if module_docstring:
        docstrings["module"] = module_docstring

    # Class and function docstrings
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                docstrings[node.name] = ast.get_docstring(node)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                docstrings[node.name] = ast.get_docstring(node)
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not method.name.startswith("_"):
                            docstrings[f"{node.name}.{method.name}"] = (
                                ast.get_docstring(method)
                            )

    return docstrings


def main():
    src_dir = "src/ushka"
    output_dir = "docs/api"

    # Clear the output directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    for root, _, files in os.walk(src_dir):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, src_dir)
                md_path = os.path.join(output_dir, rel_path.replace(".py", ".md"))

                os.makedirs(os.path.dirname(md_path), exist_ok=True)

                docstrings = generate_doc_from_file(filepath)

                with open(md_path, "w") as md_file:
                    for name, docstring in docstrings.items():
                        if docstring:
                            md_file.write(f"## `{name}`\n\n")
                            md_file.write(f"```python\n{docstring.strip()}\n```\n\n")


if __name__ == "__main__":
    main()