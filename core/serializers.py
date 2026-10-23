from rest_framework import serializers
from core.models import AnalyticsMetric

class AnalyticsMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsMetric
        fields = ['id', 'metric_name', 'value', 'timestamp']

    def create(self, validated_data):
        # Implicitly binds data being saved to the active logged-in user's company
        validated_data['tenant'] = self.context['request'].user.tenant
        return super().create(validated_data)
