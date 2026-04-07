import { ShipmentEvent } from './shipment-event.model';

export type OrderStatus =
  | 'Picked Up'
  | 'In Transit'
  | 'Out for Delivery'
  | 'Delivered'
  | 'Delayed'
  | 'Exception';

export type ServiceType =
  | 'Ground'
  | 'Express'
  | 'Overnight'
  | 'International'
  | 'FedEx Ground'
  | 'FedEx Express'
  | 'FedEx Overnight'
  | 'FedEx 2Day'
  | 'FedEx International';

export interface Order {
  id: string;
  business_id: string;
  tracking_number: string;
  origin: string;
  destination: string;
  status: OrderStatus;
  weight_lbs: number;
  service_type: ServiceType;
  estimated_delivery: string;
  actual_delivery: string | null;
  shipment_events?: ShipmentEvent[];
  updated_at: string;
}

export interface OrderStats {
  total: number;
  in_transit: number;
  delivered: number;
  delayed: number;
  exception: number;
  out_for_delivery: number;
  picked_up: number;
}

export interface PaginatedOrders {
  orders: Order[];
  total: number;
  page: number;
  limit: number;
}
