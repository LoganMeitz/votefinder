import ast
import re
import sys


def convert_format_to_fstring(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        format_string = node.func.value.s
        placeholders = re.findall(r"{([^}]*)}", format_string)
        if len(placeholders) > 0:
            f_string = format_string
            for placeholder in placeholders:
                f_string = f_string.replace("{" + placeholder + "}", "{" + placeholder + "}")
            return ast.JoinedStr([ast.Str(s=f_string)])
    return node


def convert_format_calls_to_fstrings(source_code):
    tree = ast.parse(source_code)
    new_tree = ast.fix_missing_locations(ast.Module(body=[convert_format_to_fstring(node) for node in ast.walk(tree)]))
    return ast.unparse(new_tree)


def main():
    if len(sys.argv) != 2:
        print("Usage: python convert_format_to_fstring.py <file.py>")
        sys.exit(1)

    file_path = sys.argv[1]

    with open(file_path, "r") as file:
        source_code = file.read()

    converted_code = convert_format_calls_to_fstrings(source_code)

    with open(file_path, "w") as file:
        file.write(converted_code)


if __name__ == "__main__":
    main()