# Generated by Django 2.2.13 on 2020-07-17 01:09

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0008_auto_20200717_0026'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='playerstate',
            unique_together={('game', 'player')},
        ),
    ]