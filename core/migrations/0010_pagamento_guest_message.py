from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_sitecontent'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagamento',
            name='guest',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pagamentos', to='core.guest'),
        ),
        migrations.AddField(
            model_name='pagamento',
            name='message',
            field=models.TextField(blank=True, null=True),
        ),
    ]
