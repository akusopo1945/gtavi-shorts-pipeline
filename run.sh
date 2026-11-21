#!/bin/bash
cd /data/gtavi-claudecode
source ./venv/bin/activate
exec python scripts/"$@"
