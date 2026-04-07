export interface ShipmentEvent {
  id: string;
  order_id: string;
  event_type: string;
  location: string;
  description: string;
  occurred_at: string;
}
