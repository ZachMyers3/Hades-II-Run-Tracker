New-Variable -Name "PROJECT_UNDERSCORE" -Value "hades_ii_run_tracker"
New-Variable -Name "PROJECT_SLUG" -Value "hades-ii-run-tracker"
Write-Output "Cleaing up build directories"
Remove-Item .\build\* -Recurse -Force -Confirm:$false
Remove-Item .\dist\* -Recurse -Force -Confirm:$false
Write-Output "Building executables"
{ %- if cookiecutter.add_sqlalchemy_dependencies == 'y' % }
poetry run pyinstaller src/cli.py --name $PROJECT_SLUG --noconfirm --hidden-import pymssql --paths=.\src\
{ %- else % }
poetry run pyinstaller src/cli.py --name $PROJECT_SLUG --noconfirm --paths=.\src\
{ %- endif % }
Write-Output "Build complete!"
