export interface Notification {
  id: string;
  order_id: string;
  business_id: string;
  type: string;
  message: string;
  is_read: boolean;
  created_at: string;
}
