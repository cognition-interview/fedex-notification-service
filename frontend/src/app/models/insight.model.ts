export interface DeliveryInsights {
  avg_delivery_time_by_service: { service_type: string; avg_hours: number }[];
  on_time_percentage: number;
  delivery_volume_30d: { date: string; count: number }[];
  top_routes: { origin: string; destination: string; count: number }[];
  delay_breakdown: { reason: string; count: number }[];
}
