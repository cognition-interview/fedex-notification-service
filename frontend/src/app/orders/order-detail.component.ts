import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { OrderService } from '../services/order.service';
import { BusinessService } from '../services/business.service';
import { Order } from '../models/order.model';
import { Business } from '../models/business.model';
import { ShipmentEvent } from '../models/shipment-event.model';

@Component({
  selector: 'app-order-detail',
  templateUrl: './order-detail.component.html',
  styleUrls: ['./order-detail.component.scss'],
})
export class OrderDetailComponent implements OnInit {
  order: Order | null = null;
  business: Business | undefined;
  loading = true;
  notFound = false;

  constructor(
    private route: ActivatedRoute,
    private orderService: OrderService,
    private businessService: BusinessService,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.orderService.getOrderById(id).subscribe(order => {
      if (!order) { this.notFound = true; this.loading = false; return; }
      this.order = order;
      this.loading = false;
      this.businessService.getBusinessById(order.business_id).subscribe(b => {
        this.business = b;
      });
    });
  }

  statusClass(status: string): string {
    return 'badge badge-' + status.toLowerCase().replace(/ /g, '-');
  }

  formatDateTime(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit',
    });
  }

  formatDate(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  get sortedEvents(): ShipmentEvent[] {
    if (!this.order?.shipment_events) return [];
    return [...this.order.shipment_events].sort(
      (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
    );
  }
}
