#!/bin/bash
# This script fixes line endings for the compile.sh file
# to ensure it works properly in a Linux container

# Convert Windows line endings (CRLF) to Unix line endings (LF)
sed -i 's/\r$//' compile.sh 
chmod +x compile.sh
echo "Line endings fixed for compile.sh"
