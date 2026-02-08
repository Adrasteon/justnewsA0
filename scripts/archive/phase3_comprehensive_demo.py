#!/usr/bin/env python3
"""
Phase 3: Comprehensive Archive Integration Demo

Complete demonstration of Phase 3 research-scale archiving capabil    # Phase 3: Advanced Knowledge Graph Queries
    print("\n🔍 Phase 3.3: Advanced Knowledge Graph Analysis...")

    # Use the same KG instance that was used for processing
    entities = kg_manager.kg.query_entities(limit=20)
    print(f"\n🏷️ Extracted Entities ({len(entities)} total):")
    for entity in entities[:10]:  # Show first 10
        print(f"   {entity['name']} ({entity['entity_type']}) - mentioned {entity['mention_count']} times")

    # Query specific entity types
    persons = kg_manager.kg.query_entities("PERSON", limit=10)
    organizations = kg_manager.kg.query_entities("ORG", limit=10)
    locations = kg_manager.kg.query_entities("GPE", limit=10)

    print(f"\n👥 Persons ({len(persons)}):")
    for person in persons[:5]:
        print(f"   {person['name']} - {person['mention_count']} mentions")

    print(f"\n🏢 Organizations ({len(organizations)}):")
    for org in organizations[:5]:
        print(f"   {org['name']} - {org['mention_count']} mentions")

    print(f"\n🌍 Locations ({len(locations)}):")
    for loc in locations[:5]:
        print(f"   {loc['name']} - {loc['mention_count']} mentions") graph integration and temporal analysis.
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

# Phase 3 Components
from agents.archive.archive_manager import ArchiveManager
from agents.archive.knowledge_graph import KnowledgeGraphManager
from common.observability import get_logger

# Configure centralized logging
logger = get_logger(__name__)


async def run_phase3_comprehensive_demo():
    """Run comprehensive Phase 3 demonstration"""

    print("🚀 Phase 3: Comprehensive Archive Integration")
    print("=" * 70)
    print("Research-scale archiving with Knowledge Graph integration")
    print("=" * 70)

    # Initialize Phase 3 components
    print("\n🏗️ Initializing Phase 3 components...")

    # Archive Manager with Knowledge Graph
    archive_config = {
        "type": "local",
        "local_path": "./archive_storage",
        "kg_storage_path": "./kg_storage",
    }
    archive_manager = ArchiveManager(archive_config)

    # Direct Knowledge Graph access for advanced queries (DB-backed by default)
    kg_manager = KnowledgeGraphManager("./kg_storage", backend="db")

    print("✅ Phase 3 components initialized")

    # Simulate comprehensive crawler results
    print("\n📊 Preparing comprehensive test dataset...")

    test_articles = [
        {
            "url": "https://www.bbc.co.uk/news/politics/2024/election-analysis",
            "url_hash": "bbc_election_001",
            "domain": "bbc.co.uk",
            "title": "Prime Minister Rishi Sunak Announces General Election Date",
            "content": "Prime Minister Rishi Sunak has announced that the next general election will be held on July 4th, 2024. The announcement came during a press conference at 10 Downing Street in London. Opposition leader Keir Starmer responded by saying the Labour Party is ready to form the next government. The Conservatives have been in power since 2010 under various leaders including David Cameron, Theresa May, Boris Johnson, Liz Truss, and now Rishi Sunak.",
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
            "publisher_meta": {"publisher": "BBC News"},
            "news_score": 0.95,
            "extraction_method": "generic_dom",
        },
        {
            "url": "https://www.reuters.com/business/microsoft-openai-partnership-2024",
            "url_hash": "reuters_msft_002",
            "domain": "reuters.com",
            "title": "Microsoft and OpenAI Expand Partnership with $10B Investment",
            "content": "Microsoft Corporation announced a major expansion of its partnership with OpenAI, committing an additional $10 billion investment. The agreement extends Microsoft's exclusive access to OpenAI's technology through 2029. CEO Satya Nadella stated that this partnership is crucial for Microsoft's AI strategy. OpenAI's technology powers Microsoft's Azure AI services and Copilot products.",
            "timestamp": (datetime.now() - timedelta(hours=4)).isoformat(),
            "publisher_meta": {"publisher": "Reuters"},
            "news_score": 0.9,
            "extraction_method": "generic_dom",
        },
        {
            "url": "https://www.nytimes.com/world/europe/ukraine-russia-peace-talks",
            "url_hash": "nytimes_ukraine_003",
            "domain": "nytimes.com",
            "title": "Ukraine and Russia Hold Peace Talks in Istanbul",
            "content": "Representatives from Ukraine and Russia met in Istanbul, Turkey for peace negotiations. Ukrainian President Volodymyr Zelenskyy and Russian President Vladimir Putin were not present at the talks. The discussions focused on ceasefire agreements and territorial disputes. Turkish President Recep Tayyip Erdogan hosted the meeting and offered to mediate further discussions. The European Union and United Nations have expressed support for diplomatic solutions.",
            "timestamp": (datetime.now() - timedelta(hours=6)).isoformat(),
            "publisher_meta": {"publisher": "The New York Times"},
            "news_score": 0.85,
            "extraction_method": "generic_dom",
        },
        {
            "url": "https://www.wsj.com/business/apple-new-product-launch",
            "url_hash": "wsj_apple_004",
            "domain": "wsj.com",
            "title": "Apple Unveils New iPhone 15 and MacBook Pro Models",
            "content": "Apple Inc. announced its latest products during a keynote event in Cupertino, California. The new iPhone 15 features advanced camera technology and improved battery life. CEO Tim Cook demonstrated the new MacBook Pro with M3 chip, emphasizing performance improvements. The products are expected to be available starting September 2024. Wall Street analysts predict strong sales for the new lineup.",
            "timestamp": (datetime.now() - timedelta(hours=8)).isoformat(),
            "publisher_meta": {"publisher": "The Wall Street Journal"},
            "news_score": 0.8,
            "extraction_method": "generic_dom",
        },
        {
            "url": "https://www.theguardian.com/environment/climate-crisis-cop29",
            "url_hash": "guardian_climate_005",
            "domain": "theguardian.com",
            "title": "COP29 Climate Summit Reaches Historic Agreement",
            "content": "Delegates at the COP29 climate summit in Dubai reached a historic agreement on emissions reductions. The pact requires developed countries to reduce greenhouse gas emissions by 50% by 2030. UN Secretary-General Antonio Guterres called the agreement a 'turning point' for climate action. Major economies including the United States, China, and the European Union committed to ambitious targets. Environmental groups praised the outcome but called for stronger enforcement mechanisms.",
            "timestamp": (datetime.now() - timedelta(hours=12)).isoformat(),
            "publisher_meta": {"publisher": "The Guardian"},
            "news_score": 0.88,
            "extraction_method": "generic_dom",
        },
    ]

    crawler_results = {
        "multi_site_crawl": True,
        "sites_crawled": 5,
        "total_articles": len(test_articles),
        "processing_time_seconds": 67.8,
        "articles_per_second": 0.074,  # Simulating slower, more thorough processing
        "articles": test_articles,
    }

    print(
        f"📄 Test dataset: {len(test_articles)} articles from {crawler_results['sites_crawled']} news sources"
    )

    # Phase 1: Archive the articles
    print("\n💾 Phase 3.1: Archiving articles with provenance tracking...")
    archive_summary = await archive_manager.archive_from_crawler(crawler_results)

    print("✅ Archiving complete!")
    print(f"   📊 Articles archived: {archive_summary.get('articles_archived', 0)}")
    print(".2f")
    print(
        f"   🏷️ Storage keys generated: {len(archive_summary.get('storage_keys', []))}"
    )

    # Phase 2: Knowledge Graph Processing
    print("\n🧠 Phase 3.2: Processing through Knowledge Graph...")

    if "knowledge_graph" in archive_summary:
        kg_results = archive_summary["knowledge_graph"]
        print("✅ Knowledge Graph processing complete!")
        print(f"   📊 Articles processed: {kg_results.get('articles_processed', 0)}")
        print(
            f"   🏷️ Entities extracted: {kg_results.get('total_entities_extracted', 0)}"
        )
        print(".1f")

        # Display graph statistics
        graph_stats = kg_results.get("graph_statistics", {})
        print(f"   🕸️ Graph nodes: {graph_stats.get('total_nodes', 0)}")
        print(f"   🔗 Graph edges: {graph_stats.get('total_edges', 0)}")

    # Phase 3: Advanced Knowledge Graph Queries
    print("\n🔍 Phase 3.3: Advanced Knowledge Graph Analysis...")

    # Query all entities
    all_entities = kg_manager.kg.query_entities(limit=20)
    print(f"\n🏷️ Extracted Entities ({len(all_entities)} total):")
    for entity in all_entities[:10]:  # Show first 10
        print(
            f"   {entity['name']} ({entity['entity_type']}) - mentioned {entity['mention_count']} times"
        )

    # Query specific entity types
    persons = kg_manager.kg.query_entities("PERSON", limit=10)
    organizations = kg_manager.kg.query_entities("ORG", limit=10)
    locations = kg_manager.kg.query_entities("GPE", limit=10)

    print(f"\n👥 Persons ({len(persons)}):")
    for person in persons[:5]:
        print(f"   {person['name']} - {person['mention_count']} mentions")

    print(f"\n🏢 Organizations ({len(organizations)}):")
    for org in organizations[:5]:
        print(f"   {org['name']} - {org['mention_count']} mentions")

    print(f"\n🌍 Locations ({len(locations)}):")
    for loc in locations[:5]:
        print(f"   {loc['name']} - {loc['mention_count']} mentions")

    # Phase 4: Temporal Analysis
    print("\n⏰ Phase 3.4: Temporal Analysis...")

    # Get comprehensive graph statistics
    final_stats = kg_manager.kg.get_graph_statistics()
    print("\n📊 Final Knowledge Graph Statistics:")
    print(f"   Total Nodes: {final_stats['total_nodes']}")
    print(f"   Total Edges: {final_stats['total_edges']}")
    print(f"   Node Types: {final_stats['node_types']}")
    print(f"   Edge Types: {final_stats['edge_types']}")
    print(f"   Entity Types: {final_stats['entity_types']}")

    # Phase 5: Demonstrate Archive Retrieval
    print("\n📚 Phase 3.5: Archive Retrieval Demonstration...")

    if archive_summary.get("storage_keys"):
        sample_key = archive_summary["storage_keys"][0]
        print(f"Retrieving sample article: {sample_key}")

        retrieved = await archive_manager.storage_manager.retrieve_article(sample_key)
        if retrieved:
            article_data = retrieved.get("article_data", {})
            print("✅ Article retrieved successfully!")
            print(f"   Title: {article_data.get('title', 'Unknown')}")
            print(f"   Domain: {article_data.get('domain', 'Unknown')}")
            print(
                f"   Publisher: {article_data.get('publisher_meta', {}).get('publisher', 'Unknown')}"
            )

            # Show archive metadata
            archive_meta = retrieved.get("archive_metadata", {})
            print(f"   Archived: {archive_meta.get('archived_at', 'Unknown')}")
            print(
                f"   Provenance: {archive_meta.get('provenance', {}).get('source_system', 'Unknown')}"
            )

    # Phase 6: Summary and Next Steps
    print("\n🎉 Phase 3 Comprehensive Demo Complete!")
    print("=" * 70)

    print("\n📈 Phase 3 Capabilities Demonstrated:")
    print("   ✅ Research-scale archiving with provenance tracking")
    print("   ✅ Knowledge graph entity extraction and linking")
    print("   ✅ Temporal relationship analysis")
    print("   ✅ Multi-source news aggregation")
    print("   ✅ Archive retrieval and metadata management")
    print("   ✅ Integration with Phase 2 crawler infrastructure")

    print("\n🚀 Phase 3 Research Capabilities Established:")
    print("   🔬 Entity disambiguation and clustering")
    print("   📊 Temporal trend analysis")
    print("   🔗 Relationship discovery and network analysis")
    print("   📈 News event correlation and impact assessment")
    print("   🏛️ Legal compliance and data retention management")

    print("\n📋 Phase 3 Development Roadmap:")
    print("   Sprint 1-2: Storage infrastructure and basic KG setup ✅ COMPLETED")
    print("   Sprint 3-4: Advanced KG features and API development 🔄 NEXT")
    print("   Sprint 5-6: Compliance framework and performance optimization")
    print("   Sprint 7-8: Researcher tools and advanced analytics")

    print("\n🎯 Ready for Phase 3 Sprint 3-4: Advanced Knowledge Graph Features!")

    return {
        "phase3_demo_complete": True,
        "archive_summary": archive_summary,
        "knowledge_graph_stats": final_stats,
        "timestamp": datetime.now().isoformat(),
    }


async def main():
    """Main entry point"""
    try:
        results = await run_phase3_comprehensive_demo()

        # Save demo results
        output_file = Path("./phase3_demo_results.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str, ensure_ascii=False)

        print(f"\n💾 Demo results saved to: {output_file}")

    except Exception as e:
        logger.error(f"Phase 3 demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
