import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { BusinessService } from '../services/business.service';
import { Business } from '../models/business.model';

@Component({
  selector: 'app-businesses',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './businesses.component.html',
  styleUrl: './businesses.component.scss',
})
export class BusinessesComponent implements OnInit {
  businesses: Business[] = [];
  total = 0;
  page = 1;
  readonly limit = 10;
  loading = true;

  constructor(
    private businessService: BusinessService,
    private router: Router,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    console.log('[BusinessesComponent] ngOnInit');
    this.load();
  }

  load(): void {
    this.loading = true;
    console.log('[BusinessesComponent] load start', { page: this.page, limit: this.limit, at: new Date().toISOString() });
    this.businessService.getBusinesses(this.page, this.limit).subscribe(result => {
      console.log('[BusinessesComponent] load response', {
        received: result.businesses.length,
        total: result.total,
        at: new Date().toISOString(),
      });
      this.businesses = result.businesses;
      this.total = result.total;
      this.loading = false;
      this.cdr.detectChanges();
      console.log('[BusinessesComponent] state assigned', {
        businessesLength: this.businesses.length,
        loading: this.loading,
        at: new Date().toISOString(),
      });
    });
  }

  get totalPages(): number { return Math.ceil(this.total / this.limit); }
  get pageStart(): number { return (this.page - 1) * this.limit + 1; }
  get pageEnd(): number { return Math.min(this.page * this.limit, this.total); }

  prevPage(): void { if (this.page > 1) { this.page--; this.load(); } }
  nextPage(): void { if (this.page < this.totalPages) { this.page++; this.load(); } }

  viewOrders(businessId: string): void {
    console.log('[BusinessesComponent] viewOrders click', { businessId, at: new Date().toISOString() });
    this.businessService.setSelectedBusinessId(businessId);
    this.router.navigate(['/orders'], { queryParams: { businessId } });
  }
}
