import { Component } from '@angular/core';
import { OrderService } from '../services/order.service';
import { Order, OrderStatus } from '../models/order.model';

const TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  'Picked Up': ['In Transit'],
  'In Transit': ['Out for Delivery', 'Delayed', 'Exception'],
  'Out for Delivery': ['Delivered', 'Delayed', 'Exception'],
  'Delayed': ['In Transit', 'Out for Delivery', 'Exception'],
  'Exception': ['In Transit', 'Out for Delivery', 'Delivered'],
  'Delivered': [],
};

@Component({
  selector: 'app-update-status',
  templateUrl: './update-status.component.html',
  styleUrls: ['./update-status.component.scss'],
})
export class UpdateStatusComponent {
  trackingInput = '';
  order: Order | null = null;
  lookupError = '';
  looking = false;

  newStatus: OrderStatus | '' = '';
  location = '';
  description = '';

  submitting = false;
  successMessage = '';
  submitError = '';

  get allowedTransitions(): OrderStatus[] {
    if (!this.order) return [];
    return TRANSITIONS[this.order.status] ?? [];
  }

  constructor(private orderService: OrderService) {}

  lookup(): void {
    const tracking = this.trackingInput.trim();
    if (!tracking) return;
    this.lookupError = '';
    this.order = null;
    this.successMessage = '';
    this.submitError = '';
    this.looking = true;

    this.orderService.getOrders({ search: tracking, page: 1, limit: 20 }).subscribe(result => {
      if (result.orders.length > 0) {
        const normalized = tracking.replace(/\s+/g, '').toLowerCase();
        this.order = result.orders.find(
          o => o.tracking_number.replace(/\s+/g, '').toLowerCase() === normalized,
        ) ?? result.orders[0];
      }

      if (!this.order) {
        this.lookupError = 'Order not found. Check the tracking number and try again.';
      }

      this.looking = false;
      this.newStatus = '';
      this.location = this.order?.origin ?? '';
      this.description = '';
    });
  }

  submit(): void {
    if (!this.order || !this.newStatus) return;
    this.submitting = true;
    this.submitError = '';
    this.successMessage = '';

    const payload = {
      status: this.newStatus,
      location: this.location,
      description: this.description,
    };

    const prevStatus = this.order.status;
    this.orderService.updateOrderStatus(this.order.id, payload).subscribe({
      next: updatedOrder => {
        this.order = updatedOrder;
        this.successMessage = `Status updated from "${prevStatus}" -> "${updatedOrder.status}".`;
        this.newStatus = '';
        this.location = this.order?.origin ?? '';
        this.description = '';
        this.submitting = false;
      },
      error: () => {
        this.submitError = 'Failed to update status. Please try again.';
        this.submitting = false;
      },
    });
  }

  statusClass(status: string): string {
    return 'badge badge-' + status.toLowerCase().replace(/ /g, '-');
  }

  formatDate(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }
}
