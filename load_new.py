#!/usr/bin/env python3
"""
Quick Loader for Essential Pakistani Laws
Load Essential_Laws_Complete.json into ChromaDB in 2 minutes!
"""

import json
import chromadb
from chromadb.utils import embedding_functions


def load_essential_laws():
    """Load essential laws JSON into ChromaDB"""
    
    print("🚀 Loading Essential Pakistani Laws...")
    print("📦 Connecting to ChromaDB...")

    # ✅ Use the new PersistentClient (replaces Client + Settings)
    client = chromadb.PersistentClient(path="./chroma_db")

    # ✅ Define an embedding function (recommended)
    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # Get or create collection
    collection = client.get_or_create_collection(
        name="pakistani_laws",
        embedding_function=embedding_function
    )
    print(f"✅ Connected to collection: {collection.name}")

    # Load the JSON file
    print("📄 Reading Essential_Laws_Complete.json...")
    try:
        with open('Essential_laws.json', 'r', encoding='utf-8') as f:
            laws_data = json.load(f)
        print(f"✅ Loaded {len(laws_data)} law documents")
    except FileNotFoundError:
        print("❌ ERROR: Essential_Laws_Complete.json not found!")
        print("   Make sure the file is in the same directory as this script.")
        return

    # Prepare documents for ChromaDB
    print("🔨 Processing sections...")
    documents, metadatas, ids = [], [], []
    doc_id = 0

    for law in laws_data:
        law_name = law.get('law_name', 'Unknown Law')
        sections = law.get('sections', [])
        print(f"  Processing: {law_name} ({len(sections)} sections)")

        for section in sections:
            title = section.get('title', 'Untitled')
            content = section.get('content', '')
            section_path = section.get('section_path', [])
            source = section.get('source', 'Unknown')

            doc_text = f"{title}\n\n{content}"

            metadata = {
                'law_name': law_name,
                'title': title,
                'section_path': ' > '.join(section_path),
                'source': source
            }

            if 'metadata' in section:
                metadata.update(section['metadata'])

            documents.append(doc_text)
            metadatas.append(metadata)
            ids.append(f"essential_law_{doc_id}")
            doc_id += 1

    # Add to ChromaDB
    print(f"\n💾 Adding {len(documents)} sections to ChromaDB...")
    try:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"✅ Successfully loaded {len(documents)} sections!")
    except Exception as e:
        print(f"❌ Error adding to ChromaDB: {e}")
        return

    # Verify
    print("\n🔍 Verifying...")
    total_count = collection.count()
    print(f"   Total documents in collection: {total_count}")

    # Test query
    print("\n🧪 Running test query: 'theft property'...")
    results = collection.query(
        query_texts=["theft property"],
        n_results=3
    )

    if results.get('documents') and results['documents'][0]:
        print(f"✅ Test query successful! Found {len(results['documents'][0])} results:")
        for i, doc in enumerate(results['documents'][0][:3], 1):
            metadata = results['metadatas'][0][i - 1]
            print(f"\n   {i}. {metadata.get('law_name', 'Unknown')}")
            print(f"      {metadata.get('section_path', 'Unknown')}: {metadata.get('title', 'Unknown')}")
    else:
        print("⚠️  Test query returned no results. You may need to rebuild the collection.")

    print("\n" + "=" * 60)
    print("🎉 LOADING COMPLETE!")
    print("=" * 60)
    print("\n📋 Summary:")
    print(f"   • Loaded: {len(laws_data)} law documents")
    print(f"   • Total sections: {len(documents)}")
    print(f"   • Collection name: pakistani_laws")
    print("\n✅ Your demo is ready!")
    print("\n💡 Next Steps:")
    print("   1. Test queries in your app")
    print("   2. Verify citations are showing correctly")
    print("   3. Practice your demo script")
    print("\n🎬 Demo Queries to Try:")
    print("   • 'My uncle stole my property, what can I do?'")
    print("   • 'Police stopped me without warrant'")
    print("   • 'Someone hacked my account'")
    print("   • 'Someone broke our business contract'")
    print("\nGood luck with your demo! 🚀\n")


if __name__ == "__main__":
    load_essential_laws()
