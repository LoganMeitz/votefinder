# Generated by Django 2.2.13 on 2020-07-17 00:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0007_auto_20200717_0004'),
    ]

    operations = [
        migrations.AlterField(
            model_name='post',
            name='post_id',
            field=models.IntegerField(db_index=True),
        ),
    ]