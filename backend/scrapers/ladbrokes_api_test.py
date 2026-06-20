"""
Try different Ladbrokes GraphQL approaches to find challenge market data.
"""

import requests
import json
import hashlib

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.ladbrokes.com.au",
    "Referer": "https://www.ladbrokes.com.au/",
}

GRAPHQL_URL = "https://www.ladbrokes.com.au/graphql"

# Known operations from vendor bundle
OPERATIONS = [
    "RacingExtrasScreenWeb",
    "RacingExtraMarketsList", 
    "RacingExtrasMarket",
    "RacingRaceCardScreenWeb",
    "RacingHomeScreenWeb",
    "RacingMarketCard",
    "RacingRaceCard",
    "RacingRunnerCard",
    "RacingRunnerOdds",
]

# Known SHAs from vendor bundle (may be stale)
KNOWN_SHAS = {
    "RacingExtrasScreenWeb": "5531c5f19f2638ef",
    "RacingExtraMarketsList": "9a71cde40898f37b",
    "RacingExtrasMarket": "a49e52022fd8d591",
    "RacingRaceCardScreenWeb": "2f586937a696c739",
    "RacingHomeScreenWeb": "77c712df2987b69f",
    "RacingVideoChannels": "160653ed87b09847",
    "RacingSideMenuNextToJumpRaces": "1987eaaa847af9f1",
}

# Try to compute SHA from operation name
def compute_sha(operation_name):
    """Try different SHA computation methods."""
    sha256 = hashlib.sha256()
    sha256.update(operation_name.encode())
    return sha256.hexdigest()[:16]


def try_persisted_query(operation, sha=None):
    """Try a persisted query with given operation and SHA."""
    if not sha:
        sha = compute_sha(operation)
    
    payload = {
        "operationName": operation,
        "variables": {},
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": sha
            }
        }
    }
    
    try:
        resp = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=10)
        return resp.status_code, resp.json() if resp.status_code == 200 else resp.text
    except Exception as e:
        return None, str(e)


def try_query_with_body(operation, query_body, variables=None):
    """Try a full query with operation body."""
    payload = {
        "operationName": operation,
        "query": query_body,
        "variables": variables or {}
    }
    
    try:
        resp = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=10)
        return resp.status_code, resp.json() if resp.status_code == 200 else resp.text
    except Exception as e:
        return None, str(e)


def try_introspection():
    """Try GraphQL introspection query."""
    query = """
    query IntrospectionQuery {
        __schema {
            queryType { name }
            mutationType { name }
            types {
                name
                kind
                fields {
                    name
                }
            }
        }
    }
    """
    return try_query_with_body("IntrospectionQuery", query)


def try_racing_extras_with_different_shas():
    """Try RacingExtrasMarket with many different SHA variations."""
    # Generate candidate SHAs
    candidates = [
        # Known SHA
        "a49e52022fd8d591",
        # Computed from operation name
        compute_sha("RacingExtrasMarket"),
        # Full SHA256
        hashlib.sha256("RacingExtrasMarket".encode()).hexdigest(),
        # With different prefixes
        hashlib.sha256(("query " + "RacingExtrasMarket").encode()).hexdigest(),
        # Partial from vendor bundle (trying different lengths)
        "a49e52022fd8d591",
        "dec7453c51253bb2",
        # From vendor bundle file
        "9a71cde40898f37b",
    ]
    
    results = []
    for sha in set(candidates):
        sha_short = sha[:16]
        status, data = try_persisted_query("RacingExtrasMarket", sha_short)
        results.append({"sha": sha_short, "status": status, "data": str(data)[:200]})
        if status == 200 and isinstance(data, dict) and data.get("data"):
            print(f"SUCCESS with SHA: {sha_short}")
            print(json.dumps(data, indent=2)[:1000])
            return data
    
    return results


def try_rest_endpoints():
    """Try REST API endpoints instead of GraphQL."""
    endpoints = [
        "https://www.ladbrokes.com.au/api/racing/harness",
        "https://www.ladbrokes.com.au/api/racing/harness/today",
        "https://www.ladbrokes.com.au/api/racing/upcoming",
        "https://www.ladbrokes.com.au/api/sports/racing/harness",
        "https://api.ladbrokes.com.au/racing/harness",
        "https://www.ladbrokes.com.au/racing/api/harness",
        "https://www.ladbrokes.com.au/api/v1/racing/harness",
        "https://www.ladbrokes.com.au/api/v2/racing/harness",
    ]
    
    results = []
    for url in endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            results.append({"url": url, "status": resp.status_code, "content_type": resp.headers.get("content-type", ""), "body": resp.text[:200]})
        except Exception as e:
            results.append({"url": url, "error": str(e)})
    
    return results


def try_different_graphql_endpoints():
    """Try different GraphQL endpoints."""
    endpoints = [
        "https://www.ladbrokes.com.au/graphql",
        "https://www.ladbrokes.com.au/api/graphql",
        "https://www.ladbrokes.com.au/gateway/graphql",
        "https://graphql.ladbrokes.com.au",
        "https://api.ladbrokes.com.au/graphql",
        "https://www.ladbrokes.com.au/_next/data/graphql",
    ]
    
    # Simple query to test
    payload = {
        "operationName": "RacingHomeScreenWeb",
        "variables": {},
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": KNOWN_SHAS["RacingHomeScreenWeb"]
            }
        }
    }
    
    results = []
    for url in endpoints:
        try:
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
            results.append({"url": url, "status": resp.status_code, "body": resp.text[:200]})
        except Exception as e:
            results.append({"url": url, "error": str(e)})
    
    return results


def main():
    print("=" * 60)
    print("LADBROKES API INVESTIGATION")
    print("=" * 60)
    
    # 1. Try introspection
    print("\n1. Trying GraphQL introspection...")
    status, data = try_introspection()
    print(f"   Status: {status}")
    if status == 200:
        print(f"   Data: {str(data)[:500]}")
    
    # 2. Try known operations
    print("\n2. Trying known operations...")
    for op in OPERATIONS:
        sha = KNOWN_SHAS.get(op)
        status, data = try_persisted_query(op, sha)
        print(f"   {op}: {status}")
        if status == 200 and isinstance(data, dict):
            if data.get("data"):
                print(f"      SUCCESS: {list(data['data'].keys())}")
            elif data.get("errors"):
                print(f"      Errors: {str(data['errors'])[:100]}")
    
    # 3. Try RacingExtrasMarket with different SHAs
    print("\n3. Trying RacingExtrasMarket with different SHAs...")
    results = try_racing_extras_with_different_shas()
    print(f"   Tried {len(results)} SHAs")
    
    # 4. Try REST endpoints
    print("\n4. Trying REST endpoints...")
    rest_results = try_rest_endpoints()
    for r in rest_results:
        print(f"   {r.get('url', 'N/A')}: {r.get('status', r.get('error', 'N/A'))}")
    
    # 5. Try different GraphQL endpoints
    print("\n5. Trying different GraphQL endpoints...")
    endpoint_results = try_different_graphql_endpoints()
    for r in endpoint_results:
        print(f"   {r.get('url', 'N/A')}: {r.get('status', r.get('error', 'N/A'))}")
    
    # Save all results
    all_results = {
        "introspection": {"status": status, "data": str(data)[:1000] if data else None},
        "operations": results,
        "rest": rest_results,
        "endpoints": endpoint_results,
    }
    
    with open("/tmp/ladbrokes_api_results.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print("\n" + "=" * 60)
    print("Results saved to /tmp/ladbrokes_api_results.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
