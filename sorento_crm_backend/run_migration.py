#!/usr/bin/env python3
"""Script to run Alembic migrations."""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from alembic.config import Config
from alembic import command

def main():
    """Run Alembic migrations."""
    alembic_cfg = Config("alembic.ini")
    
    print("Running Alembic migrations...")
    print("=" * 50)
    
    # Show current revision
    print("\n1. Checking current database revision...")
    try:
        command.current(alembic_cfg)
    except Exception as e:
        print(f"   No current revision found (this is normal for a fresh database): {e}")
    
    # Upgrade to head
    print("\n2. Upgrading database to latest revision...")
    command.upgrade(alembic_cfg, "head")
    
    print("\n" + "=" * 50)
    print("Migration completed successfully!")
    print("=" * 50)

if __name__ == "__main__":
    main()
