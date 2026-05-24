import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.INFO)
from dvol_provider import DVOLProvider

d = DVOLProvider()
print("Status:", d.get_status())
print("Should trade:", d.should_trade())
