import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { OrderService } from '../services/order.service';
import { BusinessService } from '../services/business.service';
import { Order, OrderStats } from '../models/order.model';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
})
export class DashboardComponent implements OnInit {
  stats: OrderStats | null = null;
  recentOrders: Order[] = [];
  loading = true;

  constructor(
    private orderService: OrderService,
    private businessService: BusinessService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.businessService.getSelectedBusinessId().subscribe(bizId => {
      this.loading = true;
      const bid = bizId || undefined;
      this.orderService.getOrderStats(bid).subscribe(s => {
        this.stats = s;
        this.cdr.detectChanges();
      });
      this.orderService.getOrders({ businessId: bid, limit: 10 }).subscribe(result => {
        this.recentOrders = result.orders;
        this.loading = false;
        this.cdr.detectChanges();
      });
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
