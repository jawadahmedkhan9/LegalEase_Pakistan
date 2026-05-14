"""
Generic Law Loader for ChromaDB - macOS Compatible Version
Fixes CoreML/ONNX Runtime issues on macOS
"""

import json
import os
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings


class LawLoader:
    """Generic loader for Pakistani law documents into ChromaDB"""
    
    def __init__(self, chroma_db_path: str = "./chroma_db"):
        """
        Initialize the loader with ChromaDB client
        
        Args:
            chroma_db_path: Path to store the ChromaDB database
        """
        self.client = chromadb.PersistentClient(chroma_db_path)
        
    def get_embedding_function(self):
        """
        Get a compatible embedding function for macOS
        Uses default with CPU-only providers to avoid CoreML issues
        """
        try:
            # Try to use sentence-transformers if available (more reliable on macOS)
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            print("✅ Using SentenceTransformer embedding function")
            return SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2",
                device="cpu"  # Force CPU to avoid CoreML issues
            )
        except ImportError:
            # Fallback to default ONNX with CPU-only providers
            print("✅ Using default embedding function (CPU-only)")
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            
            # Create embedding function with CPU providers only
            import os
            os.environ["OMP_NUM_THREADS"] = "1"  # Prevent threading issues
            
            return DefaultEmbeddingFunction()
        
    def detect_structure(self, data: List[Dict]) -> str:
        """
        Detect if the JSON has flat or nested structure
        
        Args:
            data: Loaded JSON data
            
        Returns:
            'flat' or 'nested'
        """
        if not data:
            return 'flat'
        
        first_item = data[0]
        # Check if it has 'law_name' and 'sections' keys (nested structure)
        if 'law_name' in first_item and 'sections' in first_item:
            return 'nested'
        # Otherwise it's flat structure
        return 'flat'
    
    def process_flat_structure(self, data: List[Dict], collection_name: str) -> tuple:
        """
        Process flat structure (direct array of sections)
        
        Args:
            data: List of section dictionaries
            collection_name: Name of the collection
            
        Returns:
            Tuple of (documents, metadatas, ids)
        """
        documents = []
        metadatas = []
        ids = []
        
        for idx, section in enumerate(data):
            # Extract content
            content = section.get("content", "")
            if not content:  # Skip empty content
                continue
            
            # Create metadata
            metadata = {
                "title": section.get("title", ""),
                "source": section.get("source", ""),
                "section_path": " > ".join(section.get("section_path", [])),
                "collection": collection_name
            }
            
            # Add metadata from the metadata field
            if "metadata" in section:
                section_metadata = section["metadata"]
                for key, value in section_metadata.items():
                    if isinstance(value, (list, tuple)):
                        metadata[key] = ", ".join(str(v) for v in value)
                    elif value is not None:
                        metadata[key] = str(value)
            
            # Create unique ID
            doc_id = f"{collection_name}_{idx}"
            
            documents.append(content)
            metadatas.append(metadata)
            ids.append(doc_id)
        
        return documents, metadatas, ids
    
    def process_nested_structure(self, data: List[Dict], collection_name: str) -> tuple:
        """
        Process nested structure (law_name -> sections)
        
        Args:
            data: List of law dictionaries with sections
            collection_name: Name of the collection
            
        Returns:
            Tuple of (documents, metadatas, ids)
        """
        documents = []
        metadatas = []
        ids = []
        
        doc_counter = 0
        for law_idx, law in enumerate(data):
            law_name = law.get("law_name", f"Law_{law_idx}")
            sections = law.get("sections", [])
            
            for section_idx, section in enumerate(sections):
                # Extract content
                content = section.get("content", "")
                if not content:  # Skip empty content
                    continue
                
                # Create metadata
                metadata = {
                    "law_name": law_name,
                    "title": section.get("title", ""),
                    "source": section.get("source", ""),
                    "section_path": " > ".join(section.get("section_path", [])),
                    "collection": collection_name
                }
                
                # Add metadata from the metadata field
                if "metadata" in section:
                    section_metadata = section["metadata"]
                    for key, value in section_metadata.items():
                        if isinstance(value, (list, tuple)):
                            metadata[key] = ", ".join(str(v) for v in value)
                        elif value is not None:
                            metadata[key] = str(value)
                
                # Create unique ID
                doc_id = f"{collection_name}_{doc_counter}"
                doc_counter += 1
                
                documents.append(content)
                metadatas.append(metadata)
                ids.append(doc_id)
        
        return documents, metadatas, ids
    
    def load_law_file(self, file_path: str, collection_name: str) -> int:
        """
        Load a law JSON file into ChromaDB
        
        Args:
            file_path: Path to the JSON file
            collection_name: Name for the ChromaDB collection
            
        Returns:
            Number of documents loaded
        """
        print(f"\n{'='*60}")
        print(f"Loading: {file_path}")
        print(f"Collection: {collection_name}")
        print(f"{'='*60}")
        
        # Load JSON file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"❌ Error: File not found - {file_path}")
            return 0
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in {file_path} - {e}")
            return 0
        
        # Detect structure
        structure = self.detect_structure(data)
        print(f"📊 Detected structure: {structure.upper()}")
        
        # Process based on structure
        if structure == 'flat':
            documents, metadatas, ids = self.process_flat_structure(data, collection_name)
        else:
            documents, metadatas, ids = self.process_nested_structure(data, collection_name)
        
        if not documents:
            print(f"⚠️  Warning: No documents found in {file_path}")
            return 0
        
        print(f"📄 Preparing to load {len(documents)} documents...")
        
        # Get embedding function (macOS compatible)
        embedding_function = self.get_embedding_function()
        
        # Create or get collection with the embedding function
        collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function,
            metadata={"description": f"Pakistani {collection_name.replace('_', ' ').title()}"}
        )
        
        # Add documents to collection in smaller batches (better for macOS)
        batch_size = 100  # Smaller batches for stability on macOS
        total_loaded = 0
        
        print(f"⏳ Loading in batches of {batch_size}...")
        
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i + batch_size]
            batch_metas = metadatas[i:i + batch_size]
            batch_ids = ids[i:i + batch_size]
            
            try:
                collection.add(
                    documents=batch_docs,
                    metadatas=batch_metas,
                    ids=batch_ids
                )
                total_loaded += len(batch_docs)
                print(f"  ✅ Batch {(i//batch_size)+1}: {total_loaded}/{len(documents)} documents loaded")
            except Exception as e:
                print(f"  ❌ Error loading batch {(i//batch_size)+1}: {e}")
                # Continue with next batch
                continue
        
        print(f"✨ Successfully loaded {total_loaded} documents into '{collection_name}'")
        return total_loaded
    
    def load_all_laws(self, law_files: Dict[str, str]) -> Dict[str, int]:
        """
        Load all law files into their respective collections
        
        Args:
            law_files: Dictionary mapping collection names to file paths
            
        Returns:
            Dictionary with collection names and document counts
        """
        print("\n" + "="*60)
        print("🏛️  PAKISTANI LAWS - CHROMADB LOADER (macOS Compatible)")
        print("="*60)
        
        results = {}
        total_documents = 0
        
        for collection_name, file_path in law_files.items():
            count = self.load_law_file(file_path, collection_name)
            results[collection_name] = count
            total_documents += count
        
        # Print summary
        print("\n" + "="*60)
        print("📊 LOADING SUMMARY")
        print("="*60)
        for collection_name, count in results.items():
            status = "✅" if count > 0 else "❌"
            print(f"{status} {collection_name}: {count} documents")
        print(f"\n🎯 Total documents loaded: {total_documents}")
        print("="*60 + "\n")
        
        return results


def main():
    """Main execution function"""
    
    # Define law files and their collection names
    law_files = {
        "religious_laws": "Religious_Laws.json",
        "police_laws": "Police_Laws.json",
        "family_laws": "family_laws.json",
        "land_property_laws": "Land-Property_Law.json",
        "banking_laws": "Banking_Laws.json"
    }
    
    # Initialize loader
    loader = LawLoader(chroma_db_path="./chroma_db")
    
    # Load all laws
    results = loader.load_all_laws(law_files)
    
    # Verify collections
    print("\n📚 Available Collections in ChromaDB:")
    collections = loader.client.list_collections()
    for collection in collections:
        count = collection.count()
        print(f"  • {collection.name}: {count} documents")


if __name__ == "__main__":
    main()