import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink, ActivatedRoute, Router } from '@angular/router';
import { OrderService } from '../services/order.service';
import { BusinessService } from '../services/business.service';
import { Order, OrderStatus, ServiceType } from '../models/order.model';

@Component({
  selector: 'app-order-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './order-list.component.html',
  styleUrl: './order-list.component.scss',
})
export class OrderListComponent implements OnInit {
  orders: Order[] = [];
  total = 0;
  page = 1;
  readonly limit = 10;
  loading = false;

  filterStatus: OrderStatus | '' = '';
  filterServiceType: ServiceType | '' = '';
  filterSearch = '';

  selectedBusinessId = '';

  statuses: OrderStatus[] = ['Picked Up', 'In Transit', 'Out for Delivery', 'Delivered', 'Delayed', 'Exception'];
  serviceTypes: ServiceType[] = [
    'FedEx Ground',
    'FedEx Express',
    'FedEx Overnight',
    'FedEx 2Day',
    'FedEx International',
  ];

  constructor(
    private orderService: OrderService,
    private businessService: BusinessService,
    private route: ActivatedRoute,
    private router: Router,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    console.log('[OrderListComponent] ngOnInit');
    // Read businessId from query params (e.g. when navigated from Businesses page)
    const qp = this.route.snapshot.queryParamMap;
    const qpBizId = qp.get('businessId');
    console.log('[OrderListComponent] query params read', { businessId: qpBizId, at: new Date().toISOString() });
    if (qpBizId) {
      this.businessService.setSelectedBusinessId(qpBizId);
      // Clear query param from URL without reload
      this.router.navigate([], { queryParams: {}, replaceUrl: true });
    }

    this.businessService.getSelectedBusinessId().subscribe(id => {
      console.log('[OrderListComponent] selectedBusinessId emitted', { id, at: new Date().toISOString() });
      this.selectedBusinessId = id;
      this.page = 1;
      this.loadOrders();
    });
  }

  loadOrders(): void {
    this.loading = true;
    const filters = {
      businessId: this.selectedBusinessId || undefined,
      status: this.filterStatus || undefined,
      serviceType: this.filterServiceType || undefined,
      search: this.filterSearch || undefined,
      page: this.page,
      limit: this.limit,
    };
    console.log('[OrderListComponent] loadOrders start', { filters, at: new Date().toISOString() });
    this.orderService.getOrders({
      businessId: this.selectedBusinessId || undefined,
      status: this.filterStatus || undefined,
      serviceType: this.filterServiceType || undefined,
      search: this.filterSearch || undefined,
      page: this.page,
      limit: this.limit,
    }).subscribe(result => {
      console.log('[OrderListComponent] loadOrders response', {
        received: result.orders.length,
        total: result.total,
        at: new Date().toISOString(),
      });
      this.orders = result.orders;
      this.total = result.total;
      this.loading = false;
      this.cdr.detectChanges();
      console.log('[OrderListComponent] state assigned', {
        ordersLength: this.orders.length,
        total: this.total,
        loading: this.loading,
        at: new Date().toISOString(),
      });
    });
  }

  applyFilters(): void {
    this.page = 1;
    this.loadOrders();
  }

  prevPage(): void {
    if (this.page > 1) { this.page--; this.loadOrders(); }
  }

  nextPage(): void {
    if (this.page < this.totalPages) { this.page++; this.loadOrders(); }
  }

  get totalPages(): number {
    return Math.ceil(this.total / this.limit);
  }

  get pageStart(): number {
    return (this.page - 1) * this.limit + 1;
  }

  get pageEnd(): number {
    return Math.min(this.page * this.limit, this.total);
  }

  statusClass(status: string): string {
    return 'badge badge-' + status.toLowerCase().replace(/ /g, '-');
  }

  formatDate(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }
}
