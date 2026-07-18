from api_client import DeltaIndiaClient
from dvol_provider import DVOLProvider
from psce import PremiumSellingConditionsEngine
import time

print("Initializing API Client and DVOL Provider...")
api_client = DeltaIndiaClient()
dvol = DVOLProvider()
dvol.start()

print("Waiting 5 seconds for DVOL thread to fetch data...")
time.sleep(5)

print("Initializing PSCE...")
psce = PremiumSellingConditionsEngine(api_client, dvol)

print("Evaluating Conditions...")
result = psce.evaluate_conditions()
print(result)

print("Test complete.")
