#!/bin/sh

# This script adds the common-python-tasks package to the current project
# and updates the pyproject.toml file to include the requested tasks.

set -e

pkg="common-python-tasks"
searchOutput=$(poetry search "$pkg")
if [ "$searchOutput" = "No matching packages were found." ]; then
    printf 'Package %s not found\n' "$pkg" >&2
    exit 1
fi
ver=$(printf "%s" "$searchOutput" | awk -v p="$pkg" '$1==p{print $2}' | tail -n1)
if [ -n "$ver" ]; then
    poetry add --group dev "$pkg==$ver" || exit 1
else
    printf 'Error parsing version for %s\n' "$pkg" >&2
    exit 1
fi

script=$([ -n "$TAGS_TO_INCLUDE" ] && python -c "import sys; tags = sys.argv[1].split(); print('common_python_tasks:tasks(include_tags='+repr(tags)+')')" "$TAGS_TO_INCLUDE" || echo "common_python_tasks:tasks()")
cat >>pyproject.toml <<EOF

[tool.poe]
include_script = "$script"

EOF

printf "\n\033[1;32mCommon Python tasks added to project.\033[0m\n\n\033[1mAvailable tasks:\033[0m\n"
poe --help --ansi | awk '/Configured tasks:/ {flag=1; next} flag'
