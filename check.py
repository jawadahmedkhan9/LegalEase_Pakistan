#!/usr/bin/env python3
"""
Test Script for Essential Pakistani Laws
Verify that all laws are loaded correctly and queries work as expected
"""

import chromadb
from chromadb.utils import embedding_functions


def test_essential_laws():
    """Run comprehensive tests on loaded essential laws"""

    print("=" * 60)
    print("🧪 TESTING ESSENTIAL PAKISTANI LAWS")
    print("=" * 60)

    # Connect to ChromaDB
    print("\n1️⃣  Connecting to ChromaDB...")
    try:
        # ✅ Use new PersistentClient API
        client = chromadb.PersistentClient(path="./chroma_db")

        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        collection = client.get_or_create_collection(
            name="pakistani_laws",
            embedding_function=embedding_function
        )
        total_docs = collection.count()
        print(f"   ✅ Connected! Total documents: {total_docs}")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return

    # Test queries
    test_queries = [
        {
            "query": "My uncle stole my property, what can I do?",
            "expected_laws": ["Pakistan Penal Code", "Specific Relief Act", "Criminal Procedure"],
            "description": "Property Theft Case"
        },
        {
            "query": "Police stopped me without warrant",
            "expected_laws": ["Criminal Procedure", "Constitution"],
            "description": "Police Arrest Without Warrant"
        },
        {
            "query": "Someone hacked my account",
            "expected_laws": ["Prevention of Electronic Crimes", "Pakistan Penal Code"],
            "description": "Cyber Crime / Hacking"
        },
        {
            "query": "Someone broke our business contract",
            "expected_laws": ["Contract Act", "Civil Procedure"],
            "description": "Breach of Contract"
        },
        {
            "query": "I got stopped for drunk driving",
            "expected_laws": ["Motor Vehicles"],
            "description": "Traffic Violation"
        },
        {
            "query": "Defective product caused me injury",
            "expected_laws": ["Consumer Protection"],
            "description": "Consumer Rights"
        },
        {
            "query": "Can police search my house without permission?",
            "expected_laws": ["Criminal Procedure", "Constitution"],
            "description": "Search and Seizure"
        },
        {
            "query": "What evidence do I need in court?",
            "expected_laws": ["Qanun-e-Shahadat", "Evidence"],
            "description": "Evidence Requirements"
        }
    ]

    print("\n2️⃣  Running Test Queries...\n")

    passed_tests = 0
    failed_tests = 0

    for i, test in enumerate(test_queries, 1):
        print(f"   Test {i}: {test['description']}")
        print(f"   Query: \"{test['query']}\"")

        try:
            results = collection.query(query_texts=[test['query']], n_results=5)

            if not results.get("documents") or not results["documents"][0]:
                print(f"   ❌ FAILED: No results returned")
                failed_tests += 1
                print()
                continue

            found_laws = []
            for metadata in results.get("metadatas", [[]])[0]:
                law_name = metadata.get("law_name", "")
                if law_name not in found_laws:
                    found_laws.append(law_name)

            matches = []
            for expected in test["expected_laws"]:
                for found in found_laws:
                    if expected.lower() in found.lower():
                        matches.append(found)
                        break

            if matches:
                print(f"   ✅ PASSED: Found {len(results['documents'][0])} results")
                print(f"   📚 Laws found: {', '.join(matches[:3])}")
                passed_tests += 1
            else:
                print(f"   ⚠️  WARNING: Expected laws not in top results")
                print(f"   📚 Got: {', '.join(found_laws[:3])}")
                print(f"   📚 Expected: {', '.join(test['expected_laws'])}")
                failed_tests += 1

        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            failed_tests += 1

        print()

    # Coverage test
    print("\n3️⃣  Checking Law Coverage...\n")

    expected_laws = [
        "Pakistan Penal Code (PPC), 1860",
        "Code of Criminal Procedure (CrPC), 1898",
        "Code of Civil Procedure (CPC), 1908",
        "Contract Act, 1872",
        "Specific Relief Act, 1877",
        "Qanun-e-Shahadat (Evidence) Order, 1984",
        "Constitution of Islamic Republic of Pakistan, 1973",
        "Prevention of Electronic Crimes Act (PECA), 2016",
        "Motor Vehicles Ordinance, 1965",
        "Consumer Protection Act"
    ]

    found_coverage = []

    for law_name in expected_laws:
        try:
            results = collection.query(query_texts=[law_name], n_results=1)
            if results.get("metadatas") and results["metadatas"][0]:
                found_law = results["metadatas"][0][0].get("law_name", "")
                if law_name.split(",")[0] in found_law:
                    print(f"   ✅ {law_name}")
                    found_coverage.append(law_name)
                else:
                    print(f"   ❌ {law_name} - Not found")
            else:
                print(f"   ❌ {law_name} - Not found")
        except Exception as e:
            print(f"   ❌ {law_name} - Query error: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"\n✅ Passed Tests: {passed_tests}/{len(test_queries)}")
    print(f"❌ Failed Tests: {failed_tests}/{len(test_queries)}")
    print(f"📚 Law Coverage: {len(found_coverage)}/{len(expected_laws)} laws")
    print(f"📄 Total Documents: {total_docs}")

    # Overall status
    print("\n" + "=" * 60)
    if passed_tests == len(test_queries) and len(found_coverage) == len(expected_laws):
        print("🎉 ALL TESTS PASSED! Your demo is ready! 🚀")
    elif passed_tests >= len(test_queries) * 0.7:
        print("✅ MOSTLY WORKING - Ready for demo with minor issues")
    else:
        print("⚠️  ISSUES DETECTED - Review failed tests before demo")
    print("=" * 60)

    # Recommendations
    print("\n💡 Recommendations:")
    if passed_tests < len(test_queries):
        print("   • Review failed queries and check if laws were loaded correctly")
        print("   • Try increasing n_results in your app for better coverage")

    if len(found_coverage) < len(expected_laws):
        print("   • Some laws may not have loaded correctly")
        print("   • Re-run the loader script: python load_new.py")

    if passed_tests == len(test_queries):
        print("   • All tests passed! You're ready for the demo")
        print("   • Practice the demo script a few times")
        print("   • Test the queries in your actual app interface")

    print("\n🎬 Demo Tip:")
    print("   Start with the property theft query - it shows the most")
    print("   comprehensive results across multiple laws!")
    print()


if __name__ == "__main__":
    test_essential_laws()
