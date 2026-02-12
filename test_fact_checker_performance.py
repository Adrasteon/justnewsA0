import requests
import json
import time

url = "http://localhost:8003/fact_check"

variations = [
    "Australia is a country and a continent.", # True
    "The Great Wall of China is visible from the Moon with the naked eye.", # False
    "The James Webb Space Telescope observed a supernova in the Milky Way yesterday.", # False (likely)
    "Python 3.13 was released in October 2024.", # True
    "The Moon is made of green cheese.", # False
    "Mount Everest is the highest mountain above sea level.", # True
    "The Eiffel Tower is in Berlin.", # False
    "Water boils at 100 degrees Celsius at sea level.", # True
    "The Sun revolves around the Earth.", # False
    "Humans have 206 bones in their adult body.", # True
    "Bats are blind.", # False
    "A group of flamingos is called a 'flamboyance'.", # True
    "The capital of Canada is Toronto.", # False (Ottawa)
    "Honey never spoils.", # True
    "An octopus has three hearts.", # True
    "Stripe was founded in 1750.", # False
    "The Amazon River is the longest river in the world.", # Disputed/True (depending on source)
    "Light travels faster than sound.", # True
    "Goldfish have a three-second memory.", # False
    "Venus is the hottest planet in our solar system.", # True
    "The speed of light is 299,792,458 meters per second.", # True
    "Penguins can fly.", # False
    "The Great Fire of London was in 1666.", # True
    "A locket is a type of explosive.", # False
    "Humans have 5 senses.", # False (more than 20)
    "Oxygen is the most abundant element in the Earth's atmosphere.", # False (Nitrogen)
    "The heart of a shrimp is located in its head.", # True
    "Abraham Lincoln was the 16th US President.", # True
    "The Atlantic Ocean is the largest ocean.", # False (Pacific)
    "Bananas grow on trees.", # False (giant herbs)
    "Mount Kilimanjaro is in South Africa.", # False (Tanzania)
    "The chemical symbol for gold is Au.", # True
    "Dogs are omnivores.", # True
    "The Titanic sank in 1912.", # True
    "An equilateral triangle has three equal sides.", # True
    "Shakespeare was born in London.", # False (Stratford)
    "The capital of Brazil is Rio de Janeiro.", # False (Brasilia)
    "Mars is known as the Red Planet.", # True
    "Sound travels faster through water than through air.", # True
    "Electrons are smaller than atoms.", # True
    "The Declaration of Independence was signed in 1776.", # True
    "A slug has four noses.", # True
    "The Great Wall of China is the only man-made structure visible from space.", # False
    "The human brain stops growing at age 18.", # False
    "There are 365 days in a leap year.", # False (366)
    "Rome was founded in 753 BC.", # True
    "Dolphins are mammals.", # True
    "The Sahara is the largest desert in the world.", # False (Antarctic)
    "A double-decker bus is a type of ship.", # False
    "Zero is a positive number." # False
]

print(f"{'Fact':<60} | {'Accurate':<8} | {'Conf':<4} | {'Search(s)':<8} | {'AI(s)':<6} | {'Total(s)':<8} | {'Dedup'}")
print("-" * 125)

total_time = 0
success_count = 0
results_log = []

for fact in variations:
    start = time.time()
    try:
        response = requests.post(url, json={"fact": fact}, timeout=150)
        end = time.time()
        
        if response.status_code == 200:
            res = response.json()
            metrics = res.get("model_trace", {}).get("metrics", {})
            timings = metrics.get("timings", {})
            stats = metrics.get("source_stats", {})
            
            t_total = timings.get('total_seconds', 0)
            total_time += t_total
            success_count += 1
            
            print(f"{fact[:58]:<60} | {str(res['is_accurate']):<8} | {res['confidence']:.2f} | "
                  f"{timings.get('collection_seconds', 0):>8} | {timings.get('evaluation_seconds', 0):>6} | "
                  f"{t_total:>8} | {stats.get('duplicate_removed', 0)}")
            results_log.append(res)
        else:
            print(f"{fact[:58]:<60} | ERROR {response.status_code}")
    except Exception as e:
        print(f"{fact[:58]:<60} | EXCEPTION: {e}")

print("-" * 125)
if success_count > 0:
    avg_time = total_time / success_count
    print(f"\nSummary:")
    print(f"Total Facts Checked: {len(variations)}")
    print(f"Successful Requests: {success_count}")
    print(f"Average Processing Time: {avg_time:.2f} seconds")
    
    true_count = sum(1 for r in results_log if r['is_accurate'])
    false_count = success_count - true_count
    print(f"Identified as True: {true_count}")
    print(f"Identified as False: {false_count}")
