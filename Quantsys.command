#!/bin/bash
cd "$(dirname "$0")"
exec python quantsys/web/app.py
