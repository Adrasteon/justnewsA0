#!/usr/bin/env python
"""
Database Population Script for Deployment Simulation

Populates the development/simulation database with realistic test data
for training and integration testing.
"""

import os
import sys
import django
import json
from pathlib import Path
from datetime import datetime, timedelta
import random

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'justnews_publisher.settings')
sys.path.insert(0, '/app')

django.setup()

from django.contrib.auth.models import User
from django.db import transaction

# Import models (adjust imports based on actual project structure)
try:
    from agents.models import Source, Document
    from memory.models import Embedding
    from training_system.models import TrainingJob, TrainingMetrics
except ImportError:
    print("Warning: Some models not found. Creating minimal models.")
    Source = None
    Document = None
    Embedding = None


class DatabasePopulator:
    """Populates database with test data for simulation"""
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.created_count = {}
    
    def log(self, message, level='INFO'):
        """Log message if verbose"""
        if self.verbose:
            print(f"[{level}] {message}")
    
    @transaction.atomic
    def populate_users(self, count=5):
        """Create test users"""
        self.log(f"Creating {count} test users...")
        
        users = []
        for i in range(count):
            username = f"testuser_{i+1}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f"{username}@simulation.local",
                    'first_name': f"Test",
                    'last_name': f"User{i+1}",
                    'is_active': True,
                }
            )
            
            if created:
                user.set_password('test_password_123')
                user.save()
                users.append(user)
                self.log(f"  ✓ Created user: {username}")
            else:
                self.log(f"  - User already exists: {username}")
        
        self.created_count['users'] = len(users)
        return users
    
    @transaction.atomic
    def populate_sources(self, count=10):
        """Create test news sources"""
        if Source is None:
            self.log("Source model not available, skipping sources", 'WARNING')
            return []
        
        self.log(f"Creating {count} test sources...")
        
        sources_data = [
            {'name': 'TechCrunch', 'url': 'https://techcrunch.com'},
            {'name': 'HackerNews', 'url': 'https://news.ycombinator.com'},
            {'name': 'ArXiv', 'url': 'https://arxiv.org'},
            {'name': 'Medium', 'url': 'https://medium.com'},
            {'name': 'Dev.to', 'url': 'https://dev.to'},
            {'name': 'Reddit - MachineLearning', 'url': 'https://reddit.com/r/MachineLearning'},
            {'name': 'The Verge', 'url': 'https://theverge.com'},
            {'name': 'Wired', 'url': 'https://wired.com'},
            {'name': 'Ars Technica', 'url': 'https://arstechnica.com'},
            {'name': 'Slashdot', 'url': 'https://slashdot.org'},
        ]
        
        sources = []
        for source_data in sources_data[:count]:
            source, created = Source.objects.get_or_create(
                name=source_data['name'],
                defaults={
                    'url': source_data['url'],
                    'is_active': True,
                    'crawl_interval': random.choice([6, 8, 12, 24]),
                }
            )
            
            if created:
                sources.append(source)
                self.log(f"  ✓ Created source: {source_data['name']}")
            else:
                self.log(f"  - Source already exists: {source_data['name']}")
        
        self.created_count['sources'] = len(sources)
        return sources
    
    @transaction.atomic
    def populate_documents(self, count=50, sources=None):
        """Create test documents"""
        if Document is None:
            self.log("Document model not available, skipping documents", 'WARNING')
            return []
        
        self.log(f"Creating {count} test documents...")
        
        if not sources:
            sources = Source.objects.all()[:5] if Source else []
        
        if not sources:
            self.log("No sources available for documents", 'WARNING')
            return []
        
        documents = []
        titles_data = [
            'Breakthrough in Machine Learning',
            'New GPU Architecture Released',
            'Python 3.13 Features',
            'Quantum Computing Progress',
            'AI Safety Concerns',
            'Database Optimization Techniques',
            'Cloud Computing Trends',
            'Cybersecurity Best Practices',
            'Open Source Projects',
            'Data Science Workflows',
        ]
        
        for i in range(count):
            title = f"{titles_data[i % len(titles_data)]} - Article {i+1}"
            content = f"""
            Sample content for document {i+1}.
            
            This is a test document created for simulation purposes. It contains
            realistic sample text that would typically be scraped from news sources.
            
            The document includes multiple paragraphs and various topics related to
            technology, machine learning, and software development.
            
            This testing scenario ensures the system can properly ingest, process,
            and index documents for the training pipeline.
            """
            
            source = random.choice(sources) if sources else None
            
            try:
                doc, created = Document.objects.get_or_create(
                    title=title,
                    defaults={
                        'content': content,
                        'source': source,
                        'url': f"https://example.com/article-{i+1}",
                        'published_at': datetime.now() - timedelta(days=random.randint(0, 30)),
                        'ingested_at': datetime.now(),
                    }
                )
                
                if created:
                    documents.append(doc)
                    if i % 10 == 0:
                        self.log(f"  ✓ Created {i+1}/{count} documents")
            except Exception as e:
                self.log(f"  ✗ Error creating document: {e}", 'ERROR')
        
        self.created_count['documents'] = len(documents)
        return documents
    
    @transaction.atomic
    def populate_embeddings(self, count=100):
        """Create test embeddings (simulated)"""
        if Embedding is None:
            self.log("Embedding model not available, skipping embeddings", 'WARNING')
            return []
        
        self.log(f"Creating {count} test embeddings (simulated)...")
        
        if Document is None:
            self.log("Document model not available, cannot create embeddings", 'WARNING')
            return []
        
        documents = Document.objects.all()[:count]
        
        if not documents:
            self.log("No documents available for embedding", 'WARNING')
            return []
        
        embeddings = []
        for i, doc in enumerate(documents):
            # Create simulated embedding (random vector)
            embedding_vector = [round(random.uniform(-1, 1), 6) for _ in range(384)]
            
            try:
                embed, created = Embedding.objects.get_or_create(
                    document=doc,
                    defaults={
                        'vector': embedding_vector,
                        'model': 'sentence-transformers/all-MiniLM-L6-v2',
                        'created_at': datetime.now(),
                    }
                )
                
                if created:
                    embeddings.append(embed)
                    if i % 20 == 0:
                        self.log(f"  ✓ Created {i+1}/{len(documents)} embeddings")
            except Exception as e:
                self.log(f"  ✗ Error creating embedding: {e}", 'ERROR')
        
        self.created_count['embeddings'] = len(embeddings)
        return embeddings
    
    @transaction.atomic
    def populate_training_jobs(self, count=3):
        """Create test training jobs"""
        try:
            TrainingJob
        except NameError:
            self.log("TrainingJob model not available, skipping training jobs", 'WARNING')
            return []
        
        self.log(f"Creating {count} test training jobs...")
        
        jobs = []
        job_configs = [
            {
                'name': 'Initial Training Run',
                'model_type': 'qlora',
                'config': {
                    'learning_rate': 2e-4,
                    'epochs': 3,
                    'batch_size': 4,
                    'warmup_steps': 100,
                }
            },
            {
                'name': 'Fine-tune v2',
                'model_type': 'qlora',
                'config': {
                    'learning_rate': 1e-4,
                    'epochs': 5,
                    'batch_size': 8,
                    'warmup_steps': 200,
                }
            },
            {
                'name': 'LoRA Adaptation',
                'model_type': 'lora',
                'config': {
                    'rank': 16,
                    'alpha': 32,
                    'dropout': 0.05,
                    'target_modules': 'q_proj,v_proj',
                }
            },
        ]
        
        for i, job_config in enumerate(job_configs[:count]):
            try:
                job, created = TrainingJob.objects.get_or_create(
                    name=job_config['name'],
                    defaults={
                        'model_type': job_config['model_type'],
                        'status': 'INITIALIZED',
                        'config': job_config['config'],
                        'created_at': datetime.now() - timedelta(days=random.randint(0, 7)),
                    }
                )
                
                if created:
                    jobs.append(job)
                    self.log(f"  ✓ Created training job: {job_config['name']}")
                    
                    # Create some metrics for the job
                    for epoch in range(1, 3):
                        TrainingMetrics.objects.get_or_create(
                            job=job,
                            epoch=epoch,
                            defaults={
                                'loss': 2.5 - (epoch * 0.3),
                                'accuracy': 0.5 + (epoch * 0.15),
                                'validation_loss': 2.6 - (epoch * 0.25),
                                'validation_accuracy': 0.48 + (epoch * 0.15),
                            }
                        )
                        self.log(f"    - Added metrics for epoch {epoch}")
                else:
                    self.log(f"  - Training job already exists: {job_config['name']}")
            except Exception as e:
                self.log(f"  ✗ Error creating training job: {e}", 'ERROR')
        
        self.created_count['training_jobs'] = len(jobs)
        return jobs
    
    def populate_all(self, **options):
        """Populate all test data"""
        print("\n" + "="*60)
        print("DATABASE POPULATION SCRIPT")
        print("="*60 + "\n")
        
        self.log("Starting database population...")
        self.log(f"Environment: {os.environ.get('ENVIRONMENT', 'unknown')}")
        self.log(f"Database: {os.environ.get('MARIADB_DB', 'unknown')}\n")
        
        try:
            # Create users
            users = self.populate_users(options.get('users', 5))
            
            # Create sources
            sources = self.populate_sources(options.get('sources', 10))
            
            # Create documents
            documents = self.populate_documents(
                options.get('documents', 50),
                sources=sources
            )
            
            # Create embeddings
            embeddings = self.populate_embeddings(options.get('embeddings', 100))
            
            # Create training jobs
            jobs = self.populate_training_jobs(options.get('training_jobs', 3))
            
            # Print summary
            print("\n" + "="*60)
            print("POPULATION SUMMARY")
            print("="*60)
            print(f"✓ Users created: {self.created_count.get('users', 0)}")
            print(f"✓ Sources created: {self.created_count.get('sources', 0)}")
            print(f"✓ Documents created: {self.created_count.get('documents', 0)}")
            print(f"✓ Embeddings created: {self.created_count.get('embeddings', 0)}")
            print(f"✓ Training jobs created: {self.created_count.get('training_jobs', 0)}")
            print("="*60 + "\n")
            
            print("✅ Database population complete!")
            print("\nNext steps:")
            print("1. Run: python manage.py runserver")
            print("2. Visit: http://localhost:8000/")
            print("3. Start training system")
            print("4. Run integration tests\n")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Error during population: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Populate database with test data for simulation'
    )
    parser.add_argument('--users', type=int, default=5, help='Number of test users')
    parser.add_argument('--sources', type=int, default=10, help='Number of test sources')
    parser.add_argument('--documents', type=int, default=50, help='Number of test documents')
    parser.add_argument('--embeddings', type=int, default=100, help='Number of test embeddings')
    parser.add_argument('--jobs', type=int, default=3, help='Number of training jobs')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--full', action='store_true', help='Full population with defaults')
    
    args = parser.parse_args()
    
    populator = DatabasePopulator(verbose=args.verbose)
    
    options = {
        'users': args.users,
        'sources': args.sources,
        'documents': args.documents,
        'embeddings': args.embeddings,
        'training_jobs': args.jobs,
    }
    
    success = populator.populate_all(**options)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
