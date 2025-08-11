from django.db import migrations, models
import uuid


def set_temp_identifier(apps, schema_editor):
    Beneficiary = apps.get_model('core', 'Beneficiary')
    for b in Beneficiary.objects.all():
        if not getattr(b, 'identifier', None):
            b.identifier = uuid.uuid4().hex
            b.save(update_fields=['identifier'])


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='beneficiary',
            name='identifier',
            field=models.CharField(max_length=32, unique=True, db_index=True, default='', verbose_name='Identificador (CPF ou outro)'),
            preserve_default=False,
        ),
        migrations.RunPython(set_temp_identifier, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='beneficiary',
            name='organization',
            field=models.ForeignKey(null=True, blank=True, on_delete=models.SET_NULL, to='core.organization', verbose_name='Organização'),
        ),
        migrations.AlterUniqueTogether(
            name='distribution',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='distribution',
            constraint=models.UniqueConstraint(fields=['beneficiary', 'period_month'], name='uniq_distribution_per_beneficiary_month_network'),
        ),
    ]

