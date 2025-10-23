"""
Management command to check for cold leads.
Run this command daily via cron.
"""
from django.core.management.base import BaseCommand
from leads.services import cold_lead_service


class Command(BaseCommand):
    help = 'Check for conversations that have gone cold and mark them'

    def handle(self, *args, **options):
        self.stdout.write("Checking for cold leads...")
        
        cold_conversations = cold_lead_service.check_cold_leads()
        
        if cold_conversations:
            self.stdout.write(self.style.SUCCESS(
                f"✓ Marked {len(cold_conversations)} conversations as cold:"
            ))
            for conv in cold_conversations:
                self.stdout.write(f"  - {conv.prospect.first_name} ({conv.prospect.email})")
        else:
            self.stdout.write("No cold leads found.")
        
        self.stdout.write(self.style.SUCCESS("\n✓ Cold lead check complete!"))
