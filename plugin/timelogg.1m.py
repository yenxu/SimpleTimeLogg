#!/usr/bin/python3
# <swiftbar.title>Timelogg</swiftbar.title>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# Tynn inngang: SwiftBar skanner bare denne mappen, koden ligger i ../timelogg.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from timelogg.app import main  # noqa: E402

sys.exit(main(sys.argv[1:], str(Path(__file__).absolute())))
