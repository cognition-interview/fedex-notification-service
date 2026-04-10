import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, Routes } from '@angular/router';
import { OrderListComponent } from './order-list.component';
import { OrderDetailComponent } from './order-detail.component';

const routes: Routes = [
  { path: '', component: OrderListComponent },
  { path: ':id', component: OrderDetailComponent },
];

@NgModule({
  declarations: [OrderListComponent, OrderDetailComponent],
  imports: [
    CommonModule,
    FormsModule,
    RouterModule.forChild(routes),
  ]
})
export class OrdersModule {}
